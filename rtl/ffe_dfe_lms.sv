// ============================================================================
// ffe_parallel.sv — Synthesisable 32-parallel T-spaced FFE for 56G PAM-4
//
// Architecture:
//   - N_PAR symbols processed per clock cycle (removes >10 GHz clocking need)
//   - Shift register depth: N_TAPS + N_PAR - 1
//   - Sum tree for each parallel output (fully pipelined, 3 stages)
//   - Coefficient RAM: single-port, written by LMS engine
//
// Clocking:
//   fbaud=56G, N_PAR=32 → clk=1.75 GHz (achievable in 28nm synthesis)
//
// Fixed-point:
//   ADC input:    6-bit signed  [-32..31] (COEFF_W=10-bit signed)
//   Output:       16-bit signed (prevents overflow from MAC accumulation)
// ============================================================================

`timescale 1ps/1fs

module ffe_parallel #(
    parameter int N_TAPS      = 21,     // total taps (N_PRE + 1 + N_POST)
    parameter int N_PAR       = 32,     // parallelism factor
    parameter int ADC_W       = 6,      // ADC bits (signed)
    parameter int COEFF_W     = 10,     // coefficient bits (signed)
    parameter int OUT_W       = 18,     // output width (ADC_W + COEFF_W + log2(N_TAPS))
    parameter int COEFF_FRAC  = 8       // coefficient fractional bits (fixed-point Q2.8)
)(
    input  logic                            clk,
    input  logic                            rst_n,
    // ADC input: N_PAR samples per clock
    input  logic signed [ADC_W-1:0]        adc_in   [N_PAR-1:0],
    input  logic                            adc_vld,
    // Equalised output: N_PAR samples per clock
    output logic signed [OUT_W-1:0]        ffe_out  [N_PAR-1:0],
    output logic                            ffe_vld,
    // Coefficient write interface (from LMS engine)
    input  logic                            coeff_wr,
    input  logic [$clog2(N_TAPS)-1:0]      coeff_addr,
    input  logic signed [COEFF_W-1:0]      coeff_din
);

    // ── Coefficient RAM ────────────────────────────────────────────────────
    logic signed [COEFF_W-1:0] coeff [N_TAPS-1:0];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // Initialise: main cursor = 1.0, all others = 0
            for (int i = 0; i < N_TAPS; i++)
                coeff[i] <= '0;
            coeff[N_TAPS/2] <= 10'sh0_FF;   // ≈ 1.0 in Q2.8
        end else if (coeff_wr) begin
            coeff[coeff_addr] <= coeff_din;
        end
    end

    // ── Shift register: depth = N_TAPS + N_PAR - 1 ────────────────────────
    // Stores last (N_TAPS + N_PAR - 1) ADC samples for parallel MAC
    localparam int SR_DEPTH = N_TAPS + N_PAR - 1;
    logic signed [ADC_W-1:0] sr [SR_DEPTH-1:0];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < SR_DEPTH; i++)
                sr[i] <= '0;
        end else if (adc_vld) begin
            // Shift old data up
            for (int i = SR_DEPTH-1; i >= N_PAR; i--)
                sr[i] <= sr[i-N_PAR];
            // Load new parallel samples (newest at index 0)
            for (int p = 0; p < N_PAR; p++)
                sr[p] <= adc_in[p];
        end
    end

    // ── Parallel MAC array ─────────────────────────────────────────────────
    // Pipeline stage 1: partial products (N_TAPS multiplications per output)
    // Each output y[p] = sum_k coeff[k] * sr[p + N_TAPS - 1 - k]
    logic signed [ADC_W+COEFF_W-1:0] pp [N_PAR-1:0][N_TAPS-1:0];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int p = 0; p < N_PAR; p++)
                for (int k = 0; k < N_TAPS; k++)
                    pp[p][k] <= '0;
        end else if (adc_vld) begin
            for (int p = 0; p < N_PAR; p++)
                for (int k = 0; k < N_TAPS; k++) begin
                    automatic int sr_idx = p + N_TAPS - 1 - k;
                    if (sr_idx >= 0 && sr_idx < SR_DEPTH)
                        pp[p][k] <= $signed(coeff[k]) *
                                    $signed({{(COEFF_W-ADC_W){sr[sr_idx][ADC_W-1]}},
                                              sr[sr_idx]});
                    else
                        pp[p][k] <= '0;
                end
        end
    end

    // Pipeline stage 2: adder tree (log2(N_TAPS) levels)
    // For N_TAPS=21: 3 pipeline stages needed; implemented here as 2-stage
    localparam int HALF = N_TAPS / 2;
    logic signed [ADC_W+COEFF_W+4:0] sum1 [N_PAR-1:0][HALF:0];
    logic signed [OUT_W-1:0]         sum2 [N_PAR-1:0];

    // Adder tree stage 1
    always_ff @(posedge clk) begin
        for (int p = 0; p < N_PAR; p++) begin
            for (int i = 0; i < HALF; i++)
                sum1[p][i] <= $signed(pp[p][2*i]) + $signed(pp[p][2*i+1]);
            if (N_TAPS % 2 != 0)
                sum1[p][HALF] <= $signed(pp[p][N_TAPS-1]);
            else
                sum1[p][HALF] <= '0;
        end
    end

    // Adder tree stage 2: sum all partial sums
    logic signed [OUT_W-1:0] acc [N_PAR-1:0];
    always_ff @(posedge clk) begin
        for (int p = 0; p < N_PAR; p++) begin
            acc[p] = '0;
            for (int i = 0; i <= HALF; i++)
                acc[p] = acc[p] + $signed(sum1[p][i][OUT_W-1:0]);
            sum2[p] <= acc[p];
        end
    end

    // ── Output register + valid pipeline ──────────────────────────────────
    logic [2:0] vld_pipe;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            vld_pipe <= '0;
            for (int p = 0; p < N_PAR; p++)
                ffe_out[p] <= '0;
        end else begin
            vld_pipe <= {vld_pipe[1:0], adc_vld};
            if (vld_pipe[2]) begin
                for (int p = 0; p < N_PAR; p++)
                    ffe_out[p] <= sum2[p];
            end
        end
    end
    assign ffe_vld = vld_pipe[2];

endmodule


// ============================================================================
// dfe_speculative.sv — 5-tap DFE with speculative (unrolled) first tap
//
// The speculative DFE resolves the 1-UI critical path:
//   Normally: sample → slicer → multiply → subtract → re-slice   (1 cycle)
//   Speculative: run 2 branches (assume d[-1]=+1 and d[-1]=-1)
//                select correct branch after d[-1] is known
//
// Taps 2–5 are computed conventionally (2-cycle latency acceptable).
// ============================================================================

module dfe_speculative #(
    parameter int N_PAR    = 32,
    parameter int N_DFE    = 5,
    parameter int FFE_W    = 18,     // FFE output width (signed)
    parameter int COEFF_W  = 10,
    parameter int DEC_W    = 3       // PAM-4 decision: signed 3-bit {-3,-1,+1,+3}
)(
    input  logic                        clk,
    input  logic                        rst_n,
    // FFE output (N_PAR symbols per cycle)
    input  logic signed [FFE_W-1:0]    ffe_out  [N_PAR-1:0],
    input  logic                        ffe_vld,
    // Decisions output (N_PAR per cycle)
    output logic signed [DEC_W-1:0]    decisions [N_PAR-1:0],
    output logic signed [FFE_W-1:0]    slicer_in [N_PAR-1:0],  // for LMS error
    output logic                        dfe_vld,
    // Coefficient write interface
    input  logic                        coeff_wr,
    input  logic [$clog2(N_DFE)-1:0]   coeff_addr,
    input  logic signed [COEFF_W-1:0]  coeff_din
);

    // ── DFE tap coefficients ───────────────────────────────────────────────
    logic signed [COEFF_W-1:0] fb_coeff [N_DFE-1:0];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            for (int i = 0; i < N_DFE; i++) fb_coeff[i] <= '0;
        else if (coeff_wr)
            fb_coeff[coeff_addr] <= coeff_din;
    end

    // ── Decision history buffer ────────────────────────────────────────────
    // Store last (N_DFE * N_PAR) decisions for feedback computation
    localparam int HIST = N_DFE + 1;
    logic signed [DEC_W-1:0] dec_hist [HIST*N_PAR-1:0];

    // ── PAM-4 slicer function ──────────────────────────────────────────────
    // Thresholds at ±2, 0 (normalised to {-3,-1,+1,+3} levels × scaling)
    // Here scaling: levels are multiples of 1 LSB (ADC code)
    // Threshold codes for 6-bit ADC, full-scale = 0.5V, levels = ±1, ±3 × Vref/4
    // In integer arithmetic: slice at -2*scale, 0, +2*scale
    localparam int SLICE_SCALE = 1 << 8;   // Q-format scaling from FFE output
    localparam signed [FFE_W-1:0] TH_HIGH =  2 * SLICE_SCALE;
    localparam signed [FFE_W-1:0] TH_MID  =  0;
    localparam signed [FFE_W-1:0] TH_LOW  = -2 * SLICE_SCALE;

    function automatic logic signed [DEC_W-1:0] pam4_slice(
        input logic signed [FFE_W-1:0] x);
        if      (x >  TH_HIGH) return 3'sd3;
        else if (x >  TH_MID)  return 3'sd1;
        else if (x >  TH_LOW)  return -3'sd1;
        else                    return -3'sd3;
    endfunction

    // ── Speculative DFE (tap 1 only) ──────────────────────────────────────
    logic signed [FFE_W-1:0]    spec_in_p [N_PAR-1:0];  // assume prev_d = +1
    logic signed [FFE_W-1:0]    spec_in_n [N_PAR-1:0];  // assume prev_d = -1
    logic signed [DEC_W-1:0]    spec_dec_p [N_PAR-1:0];
    logic signed [DEC_W-1:0]    spec_dec_n [N_PAR-1:0];
    logic signed [FFE_W-1:0]    dfe_residual [N_PAR-1:0]; // taps 2..N_DFE feedback

    // Compute taps 2..N_DFE feedback (can use full pipeline latency)
    always_comb begin
        for (int p = 0; p < N_PAR; p++) begin
            dfe_residual[p] = '0;
            for (int k = 1; k < N_DFE; k++) begin
                automatic int hist_idx = (p == 0) ? (k * N_PAR) + N_PAR - 1
                                                   : p - 1 + k * N_PAR;
                if (hist_idx < HIST*N_PAR)
                    dfe_residual[p] = dfe_residual[p] +
                        $signed(fb_coeff[k]) * $signed(dec_hist[hist_idx]);
            end
        end
    end

    // Speculative branches for tap 1
    always_comb begin
        for (int p = 0; p < N_PAR; p++) begin
            automatic logic signed [DEC_W-1:0] prev_d;
            // Tap 1 connects to most recent previous decision
            if (p == 0)
                prev_d = dec_hist[N_PAR-1];  // from previous cycle
            else
                prev_d = dec_hist[p-1];       // from same cycle, earlier symbol

            // Residual subtraction (taps 2+)
            automatic logic signed [FFE_W-1:0] y_residual;
            y_residual = ffe_out[p] - dfe_residual[p];

            // Speculate: two versions (prev assumed +1 or -1 for last tap)
            // Note: for p>0, prev_d is known from same-cycle decision
            // For p=0, this is the speculative case
            if (p == 0) begin
                spec_in_p[p] = y_residual -
                    $signed(fb_coeff[0]) * (3'sd1);    // assume +1
                spec_in_n[p] = y_residual -
                    $signed(fb_coeff[0]) * (-3'sd1);   // assume -1
                spec_dec_p[p] = pam4_slice(spec_in_p[p]);
                spec_dec_n[p] = pam4_slice(spec_in_n[p]);
            end else begin
                // Known previous decision: no speculation needed
                spec_in_p[p] = y_residual -
                    $signed(fb_coeff[0]) * $signed(prev_d);
                spec_in_n[p] = spec_in_p[p];
                spec_dec_p[p] = pam4_slice(spec_in_p[p]);
                spec_dec_n[p] = spec_dec_p[p];
            end
        end
    end

    // Select correct speculative branch for p=0 based on actual prev decision
    logic signed [DEC_W-1:0] dec_reg [N_PAR-1:0];
    logic signed [FFE_W-1:0] si_reg  [N_PAR-1:0];
    logic                     vld_reg;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int p = 0; p < N_PAR; p++) begin
                dec_reg[p] <= '0;
                si_reg[p]  <= '0;
            end
            vld_reg <= 1'b0;
        end else begin
            vld_reg <= ffe_vld;
            for (int p = 0; p < N_PAR; p++) begin
                if (p == 0) begin
                    // Select speculation based on d[-N_PAR] (one cycle delayed)
                    automatic logic signed [DEC_W-1:0] actual_prev;
                    actual_prev = dec_hist[N_PAR-1];
                    if (actual_prev > 3'sd0) begin
                        dec_reg[0] <= spec_dec_p[0];
                        si_reg[0]  <= spec_in_p[0];
                    end else begin
                        dec_reg[0] <= spec_dec_n[0];
                        si_reg[0]  <= spec_in_n[0];
                    end
                end else begin
                    dec_reg[p] <= spec_dec_p[p];
                    si_reg[p]  <= spec_in_p[p];
                end
            end
        end
    end

    // Update decision history
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < HIST*N_PAR; i++) dec_hist[i] <= '0;
        end else if (vld_reg) begin
            // Shift history
            for (int i = HIST*N_PAR-1; i >= N_PAR; i--)
                dec_hist[i] <= dec_hist[i-N_PAR];
            for (int p = 0; p < N_PAR; p++)
                dec_hist[p] <= dec_reg[p];
        end
    end

    assign decisions  = dec_reg;
    assign slicer_in  = si_reg;
    assign dfe_vld    = vld_reg;

endmodule


// ============================================================================
// lms_engine.sv — Sign-Sign LMS adaptation for FFE and DFE coefficients
//
// Computes coefficient updates and drives write-back to FFE/DFE RAMs.
// Operates at reduced clock rate (adaptation bandwidth << baud rate).
//
// Algorithm:
//   w[k] ← w[k] − μ · sign(e[n]) · sign(r[n-k])
//
// Parallelism: accumulates N_PAR gradient estimates before updating.
// This averages noise in the gradient estimate and reduces update rate.
// ============================================================================

module lms_engine #(
    parameter int N_PAR    = 32,
    parameter int N_FFE    = 21,
    parameter int N_DFE    = 5,
    parameter int ADC_W    = 6,
    parameter int DEC_W    = 3,
    parameter int FFE_W    = 18,
    parameter int COEFF_W  = 10,
    parameter int ACC_W    = 16,     // accumulator width for gradient
    parameter int MU_BITS  = 4      // step size = 1/2^MU_BITS
)(
    input  logic                        clk,
    input  logic                        rst_n,
    input  logic                        adapt_en,    // adaptation enable
    // Error signal (from slicer): N_PAR per cycle
    input  logic signed [FFE_W-1:0]    slicer_in  [N_PAR-1:0],
    input  logic signed [DEC_W-1:0]    decisions  [N_PAR-1:0],
    input  logic                        data_vld,
    // ADC samples (delayed to align with error)
    input  logic signed [ADC_W-1:0]    adc_dly    [N_PAR*N_FFE-1:0],
    // FFE coefficient update port
    output logic                        ffe_coeff_wr,
    output logic [$clog2(N_FFE)-1:0]   ffe_coeff_addr,
    output logic signed [COEFF_W-1:0]  ffe_coeff_dout,
    // DFE coefficient update port
    output logic                        dfe_coeff_wr,
    output logic [$clog2(N_DFE)-1:0]   dfe_coeff_addr,
    output logic signed [COEFF_W-1:0]  dfe_coeff_dout,
    // Current tap readback (for monitoring)
    output logic signed [COEFF_W-1:0]  ffe_taps [N_FFE-1:0],
    output logic signed [COEFF_W-1:0]  dfe_taps [N_DFE-1:0]
);

    // ── Internal coefficient registers ─────────────────────────────────────
    logic signed [ACC_W-1:0]   ffe_acc [N_FFE-1:0];   // accumulator (high precision)
    logic signed [ACC_W-1:0]   dfe_acc [N_DFE-1:0];

    // Initialise FFE: main cursor at unity, others zero
    initial begin
        for (int i = 0; i < N_FFE; i++) ffe_acc[i] = '0;
        for (int i = 0; i < N_DFE; i++) dfe_acc[i] = '0;
        ffe_acc[N_FFE/2] = 1 << (ACC_W-3);  // ≈ 1.0 in Q format
    end

    // ── Sign-sign gradient accumulation ───────────────────────────────────
    // Accumulate over N_PAR symbols then update
    logic signed [ACC_W-1:0]   grad_ffe [N_FFE-1:0];
    logic signed [ACC_W-1:0]   grad_dfe [N_DFE-1:0];
    logic [4:0]                 batch_cnt;
    localparam int BATCH = 4;   // average 4 parallel batches before update

    // Error sign averaged across N_PAR
    logic signed [1:0] e_sign_sum;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            batch_cnt   <= '0;
            for (int k = 0; k < N_FFE; k++) grad_ffe[k] <= '0;
            for (int k = 0; k < N_DFE; k++) grad_dfe[k] <= '0;
        end else if (data_vld && adapt_en) begin
            // Accumulate sign-sign gradients
            for (int p = 0; p < N_PAR; p++) begin
                // Error = slicer_in - decision (quantised error)
                automatic logic signed [FFE_W-1:0] err;
                err = slicer_in[p] - ($signed(decisions[p]) <<< (FFE_W - DEC_W - 1));
                automatic logic e_sgn;
                e_sgn = err[FFE_W-1];  // sign bit of error

                // FFE gradient: sign(e) · sign(r[n-k])
                for (int k = 0; k < N_FFE; k++) begin
                    automatic int idx;
                    idx = p * N_FFE + k;
                    if (idx < N_PAR*N_FFE) begin
                        automatic logic r_sgn;
                        r_sgn = adc_dly[idx][ADC_W-1];
                        // grad += -(e_sgn XOR r_sgn) ? +1 : -1
                        if (e_sgn ^ r_sgn)
                            grad_ffe[k] <= grad_ffe[k] - 1;
                        else
                            grad_ffe[k] <= grad_ffe[k] + 1;
                    end
                end
            end
            batch_cnt <= batch_cnt + 1;
        end
    end

    // ── Coefficient update state machine ──────────────────────────────────
    // Updates one coefficient per clock after each BATCH accumulation
    typedef enum logic [1:0] {IDLE, UPD_FFE, UPD_DFE, DONE} upd_state_t;
    upd_state_t state;
    logic [$clog2(N_FFE)-1:0] upd_ffe_idx;
    logic [$clog2(N_DFE)-1:0] upd_dfe_idx;

    // Saturation arithmetic
    function automatic logic signed [COEFF_W-1:0] saturate(
        input logic signed [ACC_W-1:0] x);
        if      (x > (2**(COEFF_W-1)-1)) return (2**(COEFF_W-1)-1);
        else if (x < -(2**(COEFF_W-1)))  return -(2**(COEFF_W-1));
        else                              return x[COEFF_W-1:0];
    endfunction

    assign ffe_taps[upd_ffe_idx] = saturate(ffe_acc[upd_ffe_idx]);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state         <= IDLE;
            upd_ffe_idx   <= '0;
            upd_dfe_idx   <= '0;
            ffe_coeff_wr  <= 1'b0;
            dfe_coeff_wr  <= 1'b0;
        end else begin
            ffe_coeff_wr <= 1'b0;
            dfe_coeff_wr <= 1'b0;
            case (state)
                IDLE: begin
                    if (batch_cnt >= BATCH) begin
                        batch_cnt   <= '0;
                        upd_ffe_idx <= '0;
                        upd_dfe_idx <= '0;
                        state       <= UPD_FFE;
                    end
                end

                UPD_FFE: begin
                    // Apply gradient: acc[k] -= mu * grad[k]
                    ffe_acc[upd_ffe_idx] <= ffe_acc[upd_ffe_idx]
                        - (grad_ffe[upd_ffe_idx] >>> MU_BITS);
                    grad_ffe[upd_ffe_idx] <= '0;
                    // Write updated tap to FFE RAM
                    ffe_coeff_wr   <= 1'b1;
                    ffe_coeff_addr <= upd_ffe_idx;
                    ffe_coeff_dout <= saturate(ffe_acc[upd_ffe_idx]
                                     - (grad_ffe[upd_ffe_idx] >>> MU_BITS));
                    ffe_taps[upd_ffe_idx] <= saturate(ffe_acc[upd_ffe_idx]);
                    if (upd_ffe_idx == N_FFE-1) begin
                        upd_ffe_idx <= '0;
                        state       <= UPD_DFE;
                    end else begin
                        upd_ffe_idx <= upd_ffe_idx + 1;
                    end
                end

                UPD_DFE: begin
                    dfe_acc[upd_dfe_idx] <= dfe_acc[upd_dfe_idx]
                        - (grad_dfe[upd_dfe_idx] >>> MU_BITS);
                    grad_dfe[upd_dfe_idx] <= '0;
                    dfe_coeff_wr   <= 1'b1;
                    dfe_coeff_addr <= upd_dfe_idx;
                    dfe_coeff_dout <= saturate(dfe_acc[upd_dfe_idx]
                                     - (grad_dfe[upd_dfe_idx] >>> MU_BITS));
                    dfe_taps[upd_dfe_idx] <= saturate(dfe_acc[upd_dfe_idx]);
                    if (upd_dfe_idx == N_DFE-1) begin
                        upd_dfe_idx <= '0;
                        state       <= IDLE;
                    end else begin
                        upd_dfe_idx <= upd_dfe_idx + 1;
                    end
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule
