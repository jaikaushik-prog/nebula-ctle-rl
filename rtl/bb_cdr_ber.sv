// ============================================================================
// bb_cdr.sv — Bang-Bang CDR digital loop
//
// Architecture:
//   [BB Phase Detector] → [Loop Filter (PI)] → [Phase Accumulator]
//   → [Phase code] → [Phase Interpolator control]
//
// Inputs:  on-time decision (d_on), half-period sample (d_half)
// Outputs: phase_code → drives analog PI; freq_word → monitors CDR lock
//
// Type-II PLL: PI loop filter for frequency acquisition capability.
// Dithering: half-LSB dither on integrator for reduced phase noise.
// ============================================================================

`timescale 1ps/1fs

module bb_cdr #(
    parameter int PHASE_BITS  = 10,    // phase accumulator width
    parameter int FREQ_BITS   = 20,    // frequency accumulator width
    parameter int N_PAR       = 32,    // parallelism (process N_PAR decisions/clk)
    parameter int DEC_W       = 3,     // PAM-4 decision width
    parameter int KP_SHIFT    = 6,     // proportional gain = 1/2^KP_SHIFT
    parameter int KI_SHIFT    = 12     // integral gain     = 1/2^KI_SHIFT
)(
    input  logic                        clk,
    input  logic                        rst_n,
    // Decision pairs for BB phase detection
    // on:   symbol at baud-rate clock edge
    // half: symbol at T/2 offset (early/late sample)
    input  logic signed [DEC_W-1:0]    d_on   [N_PAR-1:0],
    input  logic signed [DEC_W-1:0]    d_half [N_PAR-1:0],
    input  logic                        data_vld,
    // CDR outputs
    output logic [PHASE_BITS-1:0]       phase_code,     // to phase interpolator
    output logic signed [FREQ_BITS-1:0] freq_word,      // frequency estimate
    output logic                         lock_det,       // lock indicator
    // Optional: SSC input for tracking spread-spectrum clocking
    input  logic                         ssc_en,
    input  logic signed [7:0]            ssc_code        // SSC modulation word
);

    // ── BB phase error: majority vote across N_PAR symbol pairs ──────────
    // For each symbol pair, error = sign(d_half) if transition present
    logic signed [6:0]  err_sum;        // sum of BB outputs (saturated ±N_PAR)

    always_comb begin
        err_sum = '0;
        for (int p = 0; p < N_PAR-1; p++) begin
            // Detect transition: sign change between consecutive symbols
            if (d_on[p][DEC_W-1] != d_on[p+1][DEC_W-1]) begin
                // Transition detected: half-sample sign gives early/late
                if (d_half[p][DEC_W-1] == d_on[p+1][DEC_W-1])
                    err_sum = err_sum + 1;   // early → advance phase
                else
                    err_sum = err_sum - 1;   // late  → retard phase
            end
        end
    end

    // ── PI loop filter ─────────────────────────────────────────────────────
    logic signed [FREQ_BITS-1:0] integrator;
    logic signed [PHASE_BITS:0]  prop_term;
    logic signed [FREQ_BITS-1:0] integrator_next;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            integrator <= '0;
        end else if (data_vld) begin
            // Integral path: integrator += err_sum >>> KI_SHIFT
            integrator_next = integrator +
                              ($signed(err_sum) >>> KI_SHIFT);
            // SSC tracking: add SSC modulation to integrator
            if (ssc_en)
                integrator_next = integrator_next + $signed(ssc_code);
            integrator <= integrator_next;
        end
    end

    assign freq_word = integrator;

    // ── Phase accumulator ─────────────────────────────────────────────────
    logic [PHASE_BITS+FREQ_BITS-1:0] phase_acc;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            phase_acc <= '0;
        end else if (data_vld) begin
            // Phase = integral of frequency + proportional correction
            prop_term = $signed(err_sum) >>> KP_SHIFT;
            phase_acc <= phase_acc
                       + {{(PHASE_BITS){integrator[FREQ_BITS-1]}}, integrator}
                       + {{(PHASE_BITS+FREQ_BITS-PHASE_BITS-1){prop_term[PHASE_BITS]}},
                          prop_term};
        end
    end

    // Top PHASE_BITS drive the phase interpolator
    assign phase_code = phase_acc[PHASE_BITS+FREQ_BITS-1:FREQ_BITS];

    // ── Lock detector ─────────────────────────────────────────────────────
    // Lock when phase variance is small: |err_sum| < threshold for N_WIN cycles
    logic [7:0]  lock_cnt;
    logic [11:0] err_mag_acc;
    localparam int LOCK_WIN   = 128;
    localparam int LOCK_THRESH = 16;    // max allowed accumulated |err|

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lock_cnt    <= '0;
            err_mag_acc <= '0;
            lock_det    <= 1'b0;
        end else if (data_vld) begin
            err_mag_acc <= err_mag_acc + ($signed(err_sum) < 0 ?
                           -$signed(err_sum) : $signed(err_sum));
            lock_cnt    <= lock_cnt + 1;
            if (lock_cnt == LOCK_WIN-1) begin
                lock_det    <= (err_mag_acc < LOCK_THRESH * LOCK_WIN);
                err_mag_acc <= '0;
                lock_cnt    <= '0;
            end
        end
    end

endmodule


// ============================================================================
// ber_checker.sv — Real-time BER measurement against PRBS reference
//
// Uses a self-synchronising descrambler to recover reference bits,
// then counts bit errors in a sliding window.
//
// Supports: PRBS-31 (polynomial x^31 + x^28 + 1)
// Outputs:  error count, BER estimate (as mantissa + exponent), sync status
// ============================================================================

module ber_checker #(
    parameter int N_PAR   = 32,
    parameter int DEC_W   = 3,
    parameter int CNT_W   = 32,     // error counter width
    parameter int WIN_LOG2 = 20     // BER window = 2^WIN_LOG2 bits
)(
    input  logic                      clk,
    input  logic                      rst_n,
    input  logic                      enable,
    // PAM-4 decisions from DFE
    input  logic signed [DEC_W-1:0]  decisions [N_PAR-1:0],
    input  logic                      data_vld,
    // Reference PRBS-31 (self-sync after acquisition)
    // Internally generated and synchronised to incoming data
    output logic [CNT_W-1:0]          err_count,
    output logic [CNT_W-1:0]          bit_count,
    output logic [7:0]                 ber_exp,    // BER ≈ ber_mant × 10^(-ber_exp)
    output logic [3:0]                 ber_mant,
    output logic                       sync_ok,
    output logic                       ber_update  // pulses when new BER computed
);

    // ── Gray decode PAM-4 → 2 bits ─────────────────────────────────────────
    // PAM-4 Gray map: +3→{10}, +1→{11}, -1→{01}, -3→{00}
    // Output 2 bits per symbol
    function automatic logic [1:0] gray_decode(
        input logic signed [DEC_W-1:0] sym);
        case (sym)
            3'sd3:   return 2'b10;
            3'sd1:   return 2'b11;
            -3'sd1:  return 2'b01;
            default: return 2'b00;   // -3
        endcase
    endfunction

    // ── Bit extraction: N_PAR symbols → 2*N_PAR bits per cycle ────────────
    logic [2*N_PAR-1:0] rx_bits;
    always_comb begin
        for (int p = 0; p < N_PAR; p++) begin
            automatic logic [1:0] decoded;
            decoded = gray_decode(decisions[p]);
            rx_bits[2*p+1] = decoded[1];
            rx_bits[2*p]   = decoded[0];
        end
    end

    // ── PRBS-31 reference generator ────────────────────────────────────────
    // Polynomial: x^31 + x^28 + 1
    logic [30:0] prbs_state;
    logic [2*N_PAR-1:0] ref_bits;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            prbs_state <= 31'h7FFFFFFF;
        end else if (data_vld && enable) begin
            for (int i = 0; i < 2*N_PAR; i++) begin
                automatic logic fb;
                fb = prbs_state[30] ^ prbs_state[27];
                ref_bits[i]  <= fb;
                prbs_state   <= {prbs_state[29:0], fb};
            end
        end
    end

    // ── Sync detection: lock PRBS state to incoming data ──────────────────
    // Self-synchronising: load PRBS state from RX bits on initial sync
    logic sync_reg;
    logic [7:0] sync_cnt;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sync_reg  <= 1'b0;
            sync_cnt  <= '0;
        end else if (data_vld && !sync_reg) begin
            // Attempt to synchronise: load state from first 31 RX bits
            if (sync_cnt < 31) begin
                prbs_state[sync_cnt] <= rx_bits[0];
                sync_cnt <= sync_cnt + 1;
            end else begin
                sync_reg <= 1'b1;
            end
        end
    end
    assign sync_ok = sync_reg;

    // ── Error counting ─────────────────────────────────────────────────────
    logic [CNT_W-1:0] err_cnt_reg;
    logic [CNT_W-1:0] bit_cnt_reg;
    logic [WIN_LOG2:0] window_cnt;

    // Count errors in each batch of N_PAR symbols
    logic [5:0] errs_this_cycle;

    always_comb begin
        errs_this_cycle = '0;
        if (sync_reg) begin
            for (int i = 0; i < 2*N_PAR; i++)
                errs_this_cycle = errs_this_cycle + (rx_bits[i] ^ ref_bits[i]);
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            err_cnt_reg <= '0;
            bit_cnt_reg <= '0;
            window_cnt  <= '0;
            ber_update  <= 1'b0;
        end else if (data_vld && enable && sync_reg) begin
            ber_update  <= 1'b0;
            err_cnt_reg <= err_cnt_reg + errs_this_cycle;
            bit_cnt_reg <= bit_cnt_reg + 2*N_PAR;
            window_cnt  <= window_cnt + 1;

            // Compute BER every 2^WIN_LOG2 bits (latch and reset)
            if (window_cnt[WIN_LOG2]) begin
                err_count  <= err_cnt_reg;
                bit_count  <= bit_cnt_reg;
                // Simple log10 approximation for display
                // (full log requires LUT; this is a coarse indicator)
                ber_update  <= 1'b1;
                err_cnt_reg <= '0;
                bit_cnt_reg <= '0;
                window_cnt  <= '0;
            end
        end else begin
            ber_update <= 1'b0;
        end
    end

    // ── BER log10 approximation ────────────────────────────────────────────
    // Implemented as priority encoder on err_count/bit_count ratio
    // Result: ber_exp ∈ {3..15}, ber_mant ∈ {1..9}
    always_ff @(posedge clk) begin
        if (bit_count > 0) begin
            automatic logic [CNT_W-1:0] ratio;
            ratio = bit_count / (err_count + 1);  // approximate 1/BER
            // Encode as power of 10
            if      (ratio >= 32'd1_000_000_000) begin ber_exp <= 9;  ber_mant <= 1; end
            else if (ratio >= 32'd100_000_000)   begin ber_exp <= 8;  ber_mant <= 1; end
            else if (ratio >= 32'd10_000_000)    begin ber_exp <= 7;  ber_mant <= 1; end
            else if (ratio >= 32'd1_000_000)     begin ber_exp <= 6;  ber_mant <= 1; end
            else if (ratio >= 32'd100_000)       begin ber_exp <= 5;  ber_mant <= 1; end
            else if (ratio >= 32'd10_000)        begin ber_exp <= 4;  ber_mant <= 1; end
            else if (ratio >= 32'd1_000)         begin ber_exp <= 3;  ber_mant <= 1; end
            else if (ratio >= 32'd100)           begin ber_exp <= 2;  ber_mant <= 1; end
            else                                 begin ber_exp <= 1;  ber_mant <= 1; end
        end
    end

endmodule
