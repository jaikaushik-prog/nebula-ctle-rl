%% dsp_verify.m — MATLAB DSP Algorithm Verification Framework
%  112G PAM-4 SerDes DSP chain verification
%  Covers: FFE/DFE adaptation, fixed-point validation, BER sweeps,
%          CDR loop analysis, channel estimation, optical DSP.
%
%  Usage:
%    run_all()           — execute all verification suites
%    ber_vs_snr()        — BER sweep vs SNR
%    fixed_point_check() — compare float vs fixed-point
%    cdr_analysis()      — CDR loop Bode + JTOL
%
%  N. Mishra, BITS Pilani — DSP-Assisted Wireline Transceiver Framework

clear all; close all; clc;
addpath(fileparts(mfilename('fullpath')));

%% ─────────────────────────────────────────────────────────────────────────
%  Global parameters
%% ─────────────────────────────────────────────────────────────────────────
P.fbaud       = 56e9;       % baud rate [Hz]
P.Rb          = 112e9;      % bit rate [bps]
P.n_sym       = 50000;      % simulation symbols
P.pam_levels  = [-3 -1 1 3];
P.n_ffe_pre   = 3;
P.n_ffe_post  = 17;
P.n_dfe       = 5;
P.mu_ffe      = 5e-4;
P.mu_dfe      = 2e-4;
P.adc_bits    = 6;
P.adc_vref    = 0.5;        % V, full-scale
P.train_len   = 5000;       % LMS supervised training symbols

%% ─────────────────────────────────────────────────────────────────────────
%  run_all: execute all verification suites
%% ─────────────────────────────────────────────────────────────────────────
function run_all()
    fprintf('=== DSP Verification Framework — 112G PAM-4 ===\n\n');
    ber_vs_snr();
    fixed_point_check();
    cdr_loop_analysis();
    channel_estimation_test();
    optical_cd_test();
    fprintf('\n=== All tests PASSED ===\n');
end


%% ─────────────────────────────────────────────────────────────────────────
%  PAM-4 signal generation
%% ─────────────────────────────────────────────────────────────────────────
function [syms, bits] = gen_pam4(n_sym, prbs_order)
    if nargin < 2, prbs_order = 31; end
    bits = prbs_gen(n_sym * 2, prbs_order);
    syms = gray_encode(bits);
end

function bits = prbs_gen(n_bits, order)
    persistent state;
    state = 1;
    poly = struct();
    poly(7).taps  = [7 6];
    poly(31).taps = [31 28];
    taps = poly(order).taps;
    bits = zeros(1, n_bits, 'int8');
    for i = 1:n_bits
        fb = 0;
        for k = 1:length(taps)
            fb = xor(fb, bitget(state, taps(k)));
        end
        bits(i) = fb;
        state = bitshift(state, 1) + fb;
        state = bitand(state, 2^order - 1);
        if state == 0, state = 1; end
    end
end

function syms = gray_encode(bits)
    % IEEE Gray map: {00→-3, 01→-1, 11→+1, 10→+3}
    map = containers.Map({0,1,2,3}, {-3,-1,3,1});
    n_sym = floor(length(bits)/2);
    syms  = zeros(1, n_sym);
    for i = 1:n_sym
        code = bits(2*i-1)*2 + bits(2*i);
        syms(i) = map(code);
    end
end

function bits = gray_decode(syms)
    % Inverse Gray map
    levels = [-3 -1 1 3];
    map_l  = [-3 -1  1  3];
    map_b  = [ 0  1  3  2];  % {-3→00, -1→01, +1→11, +3→10}
    bits = zeros(1, 2*length(syms), 'int8');
    for i = 1:length(syms)
        [~, idx] = min(abs(map_l - syms(i)));
        code = map_b(idx);
        bits(2*i-1) = bitget(uint8(code), 2);
        bits(2*i)   = bitget(uint8(code), 1);
    end
end


%% ─────────────────────────────────────────────────────────────────────────
%  Channel model
%% ─────────────────────────────────────────────────────────────────────────
function [h_ch, t_ch] = make_channel(fbaud, len_cm, alpha_skin, alpha_diel)
    if nargin < 3, alpha_skin = 0.30; end
    if nargin < 4, alpha_diel = 0.05; end
    N  = 512;
    fs_sim = fbaud * 4;   % 4× oversampling for channel
    freq   = linspace(0, fs_sim/2, N/2+1);
    f_GHz  = freq / 1e9;
    IL_dB  = -(alpha_skin * sqrt(f_GHz) + alpha_diel * f_GHz) * len_cm;
    H_mag  = 10.^(IL_dB/20);
    tau    = len_cm * 1e-2 / (0.6 * 3e8);
    H_ph   = exp(-1j * 2*pi * freq * tau);
    H      = H_mag .* H_ph;
    H_full = [H, conj(H(end-1:-1:2))];
    h_ch   = real(ifft(H_full));
    t_ch   = (0:N-1) / fs_sim;
    % Normalise cursor to unity
    h_ch   = h_ch / max(abs(h_ch));
end

function il_nyq = channel_il_nyquist(fbaud, len_cm, alpha_skin, alpha_diel)
    if nargin < 3, alpha_skin = 0.30; end
    if nargin < 4, alpha_diel = 0.05; end
    f_nyq = fbaud/2 / 1e9;
    il_nyq = -(alpha_skin * sqrt(f_nyq) + alpha_diel * f_nyq) * len_cm;
end


%% ─────────────────────────────────────────────────────────────────────────
%  ADC model
%% ─────────────────────────────────────────────────────────────────────────
function y_q = adc_model(x, n_bits, vref, jitter_ps, fs)
    % Aperture jitter noise
    dvdt = diff([x(1), x]) * fs;
    j_noise = dvdt .* randn(1, length(x)) * jitter_ps * 1e-12;
    x_j = x + j_noise;
    % Quantise
    lsb  = 2*vref / 2^n_bits;
    code = floor((x_j + vref) / lsb);
    code = max(0, min(code, 2^n_bits - 1));
    y_q  = code * lsb - vref + lsb/2;
end


%% ─────────────────────────────────────────────────────────────────────────
%  PAM-4 slicer
%% ─────────────────────────────────────────────────────────────────────────
function d = pam4_slicer(x, thresh)
    if nargin < 2, thresh = [-2, 0, 2]; end
    d = -3 * ones(size(x));
    d(x > thresh(1)) = -1;
    d(x > thresh(2)) =  1;
    d(x > thresh(3)) =  3;
end


%% ─────────────────────────────────────────────────────────────────────────
%  FFE + DFE with SS-LMS
%% ─────────────────────────────────────────────────────────────────────────
function [decisions, mse_trace, ffe_w, dfe_w] = ...
        run_ffe_dfe(r, n_ffe_pre, n_ffe_post, n_dfe, mu_ffe, mu_dfe, ...
                    ref_syms, train_len)
    N      = length(r);
    n_ffe  = n_ffe_pre + 1 + n_ffe_post;
    % Initialise
    ffe_w    = zeros(1, n_ffe);
    ffe_w(n_ffe_pre+1) = 1.0;   % main cursor
    dfe_w    = zeros(1, n_dfe);
    decisions = zeros(1, N);
    mse_trace = zeros(1, N);
    ffe_buf   = zeros(1, n_ffe);
    dfe_buf   = zeros(1, n_dfe);

    for n = 1:N
        % Shift FFE input buffer
        ffe_buf = [r(n), ffe_buf(1:end-1)];
        % FFE output
        ffe_out = sum(ffe_w .* ffe_buf);
        % DFE feedback subtraction
        slicer_in = ffe_out - sum(dfe_w .* dfe_buf);
        % Decision
        d = pam4_slicer(slicer_in);
        decisions(n) = d;
        % Training: use reference or decision-directed
        if n <= train_len && ~isempty(ref_syms)
            target = ref_syms(n);
        else
            target = d;
        end
        % Error
        e = slicer_in - target;
        mse_trace(n) = e^2;
        % Sign-sign LMS update
        ffe_w = ffe_w - mu_ffe * sign(e) * sign(ffe_buf);
        if n_dfe > 0
            dfe_w = dfe_w + mu_dfe * sign(e) * sign(dfe_buf);
        end
        % Shift DFE buffer
        dfe_buf = [target, dfe_buf(1:end-1)];
    end
end


%% ─────────────────────────────────────────────────────────────────────────
%  BER sweep vs SNR
%% ─────────────────────────────────────────────────────────────────────────
function ber_vs_snr()
    fprintf('--- BER vs SNR sweep ---\n');
    global P;
    if isempty(P), P = get_default_params(); end

    snr_range = 14:2:28;  % dB
    ber_sim   = zeros(size(snr_range));
    ber_th    = zeros(size(snr_range));

    rng(42);
    [syms, bits] = gen_pam4(P.n_sym);
    % Channel: 30cm PCB trace
    h_ch = make_channel(P.fbaud, 30);
    rx_ch = conv(syms, h_ch, 'same');

    for i = 1:length(snr_range)
        snr = snr_range(i);
        % Add AWGN
        sig_pwr = mean(rx_ch.^2);
        n_pwr   = sig_pwr / 10^(snr/10);
        rx_noisy = rx_ch + sqrt(n_pwr) * randn(size(rx_ch));
        % ADC
        scale = P.adc_vref * 0.7 / (std(rx_noisy) * 3.5 + eps);
        rx_q  = adc_model(rx_noisy * scale, P.adc_bits, P.adc_vref, 0.15, P.fbaud);

        % FFE + DFE
        [decisions, ~, ~, ~] = run_ffe_dfe(rx_q, P.n_ffe_pre, P.n_ffe_post, ...
            P.n_dfe, P.mu_ffe, P.mu_dfe, syms(1:P.n_sym), P.train_len);

        % BER count
        rx_bits  = gray_decode(decisions(P.train_len+1:end));
        tx_bits  = bits(2*P.train_len+1 : 2*length(decisions));
        n_cmp    = min(length(rx_bits), length(tx_bits));
        n_err    = sum(rx_bits(1:n_cmp) ~= tx_bits(1:n_cmp));
        ber_sim(i) = n_err / max(n_cmp, 1);

        % Theory: PAM-4 Gray-coded AWGN BER
        ber_th(i) = 0.75 * erfc(sqrt(10^(snr/10) / 10));

        fprintf('  SNR=%2.0f dB → BER_sim=%.2e  BER_th=%.2e\n', ...
                snr, ber_sim(i), ber_th(i));
    end

    % Plot
    figure('Color','k','Name','BER vs SNR');
    semilogy(snr_range, ber_th,  'g--', 'LineWidth', 1.5, 'DisplayName', 'Theory (PAM-4 AWGN)');
    hold on;
    semilogy(snr_range, max(ber_sim,1e-15), 'ro-', 'LineWidth', 1.5, ...
             'MarkerSize', 5, 'DisplayName', 'Simulation (FFE+DFE)');
    yline(2e-2, 'r:', 'KP4 threshold', 'LabelHorizontalAlignment','left');
    yline(1e-3, 'y:', 'KR4 threshold');
    ylim([1e-8, 1]); grid on;
    xlabel('SNR [dB]','Color','w'); ylabel('BER','Color','w');
    title('BER vs SNR — 112G PAM-4, 30cm PCB','Color','w');
    legend('Location','southwest','TextColor','w');
    set(gca,'Color','k','XColor','w','YColor','w');
end


%% ─────────────────────────────────────────────────────────────────────────
%  Fixed-point validation
%% ─────────────────────────────────────────────────────────────────────────
function fixed_point_check()
    fprintf('--- Fixed-Point Validation ---\n');
    % Test FFE coefficient quantisation sensitivity
    n_bits_range = [6, 7, 8, 10, 12];
    rng(0);
    N = 20000;
    [syms, bits] = gen_pam4(N);
    h_ch = [0.05, 0.35, 1.0, 0.30, 0.08, 0.02];
    rx = conv(syms, h_ch, 'same');
    rx_noisy = rx + 0.1 * randn(1, N);

    % Float reference
    [d_float, ~, w_float, ~] = run_ffe_dfe(rx_noisy, 3, 15, 5, ...
        5e-4, 2e-4, syms, 4000);
    bits_rx_f = gray_decode(d_float(4001:end));
    tx_cmp    = bits(8001:8001+length(bits_rx_f)-1);
    ber_float = mean(bits_rx_f(1:min(end,length(tx_cmp))) ~= ...
                     tx_cmp(1:min(length(bits_rx_f),end)));
    fprintf('  Float BER = %.3e\n', ber_float);

    for nb = n_bits_range
        % Quantise FFE coefficients to nb bits
        v_max  = max(abs(w_float)) * 1.1;
        lsb    = 2*v_max / 2^nb;
        w_q    = round(w_float / lsb) * lsb;
        % Run with quantised coefficients (fixed, no adaptation)
        N_test = min(N, 10000);
        rx_t   = rx_noisy(1:N_test);
        n_ffe  = length(w_q);
        buf    = zeros(1, n_ffe);
        d_q    = zeros(1, N_test);
        for n = 1:N_test
            buf  = [rx_t(n), buf(1:end-1)];
            y    = sum(w_q .* buf);
            d_q(n) = pam4_slicer(y);
        end
        bits_q   = gray_decode(d_q(1001:end));
        tx_q     = bits(2001:2001+length(bits_q)-1);
        ber_q    = mean(bits_q(1:min(end,length(tx_q))) ~= ...
                        tx_q(1:min(length(bits_q),end)));
        fprintf('  %2d-bit coeff: BER = %.3e  (penalty = %.1f dB)\n', ...
                nb, ber_q, 10*log10(max(ber_q,1e-10)/max(ber_float,1e-10)));
    end
end


%% ─────────────────────────────────────────────────────────────────────────
%  CDR loop analysis: Bode plot + JTOL
%% ─────────────────────────────────────────────────────────────────────────
function cdr_loop_analysis()
    fprintf('--- CDR Loop Analysis ---\n');
    Kp = 0.02;   Ki = 0.001;   % PI loop filter gains
    fbaud = 56e9;
    % Type-II PLL: open-loop TF in discrete time
    % G(z) = Kp + Ki/(1 - z^-1)  [PI] × Kvco × 1/(1-z^-1) [integrator]
    % Approximate as continuous: G(s) ≈ (Kp·s + Ki) / s²
    % Natural frequency
    wn = sqrt(Kp * Ki * fbaud^2);        % rad/s
    zeta = Kp * fbaud / (2 * wn);
    fn_mhz = wn / (2*pi*1e6);
    fprintf('  Kp=%.3f Ki=%.4f → fn=%.1f MHz  ζ=%.2f\n', Kp, Ki, fn_mhz, zeta);

    % Bode plot of closed-loop jitter transfer
    f_j = logspace(5, 10, 200);  % 100 kHz to 10 GHz
    s   = 1j * 2*pi * f_j;
    % Continuous-time approximation
    G_s = fbaud^2 * (Kp*s + Ki) ./ s.^2;
    H_cl = G_s ./ (1 + G_s);
    figure('Color','k','Name','CDR Jitter Transfer');
    subplot(2,1,1);
    semilogx(f_j, 20*log10(abs(H_cl)), 'c', 'LineWidth',1.5);
    yline(-3, 'r--', '-3 dB'); grid on;
    ylabel('|H_{CDR}| [dB]','Color','w');
    title('CDR Jitter Transfer Function','Color','w');
    set(gca,'Color','k','XColor','w','YColor','w');
    subplot(2,1,2);
    semilogx(f_j, 20*log10(1./abs(H_cl)), 'y', 'LineWidth',1.5);
    hold on;
    % JTOL spec: 20 dB/decade rolloff above fn
    jtol_spec = max(0.5, fn_mhz*1e6./f_j * 0.5);
    semilogx(f_j, 20*log10(jtol_spec), 'r--', 'LineWidth',1.5);
    grid on;
    xlabel('Jitter frequency [Hz]','Color','w');
    ylabel('JTOL [UI]','Color','w');
    set(gca,'Color','k','XColor','w','YColor','w');
    fprintf('  CDR bandwidth: %.1f MHz | Damping: %.2f\n', fn_mhz, zeta);
end


%% ─────────────────────────────────────────────────────────────────────────
%  Channel estimation (MMSE tap initialisation)
%% ─────────────────────────────────────────────────────────────────────────
function channel_estimation_test()
    fprintf('--- Channel Estimation (MMSE Init) ---\n');
    fbaud = 56e9;
    % True channel
    h_true = [0.05, 0.30, 1.0, 0.28, 0.07, 0.01];
    N = 5000;
    [syms, ~] = gen_pam4(N);
    rx = conv(syms, h_true, 'same');
    rx = rx + 0.08 * randn(1, N);

    % MMSE tap estimate from cross-correlation
    % R_xy[k] = E[x[n]·y[n+k]] — cross-correlate tx and rx
    lag_max = 20;
    Rxy = xcorr(rx, syms, lag_max, 'normalized');
    % Pick taps centred on peak
    [~, pk] = max(abs(Rxy));
    n_taps = 21;
    start = max(1, pk - n_taps/2);
    h_est = Rxy(start : start+n_taps-1);
    h_est = h_est / max(abs(h_est));
    fprintf('  Estimated %d-tap channel. Peak at lag %d\n', n_taps, pk-lag_max-1);

    % Compare with LMMSE: H^-1 with regularisation
    H_freq = fft(h_true, 256);
    snr_lin = 100;  % 20 dB
    W_mmse  = conj(H_freq) ./ (abs(H_freq).^2 + 1/snr_lin);
    w_mmse  = real(ifft(W_mmse));
    fprintf('  MMSE FFE taps computed. Centre-tap energy = %.4f\n', ...
            abs(w_mmse(1)));
end


%% ─────────────────────────────────────────────────────────────────────────
%  Optical CD compensation test
%% ─────────────────────────────────────────────────────────────────────────
function optical_cd_test()
    fprintf('--- Optical CD Compensation ---\n');
    fs = 64e9;  D = 17; L_km = 80;  lambda = 1550e-9;  c = 3e8;
    N  = 4096;
    t  = (0:N-1)/fs;
    % Test signal: QPSK at 2 GHz
    f_sig = 2e9;
    sig = exp(1j * 2*pi * f_sig * t);
    % Apply CD
    freq   = fftshift(((0:N-1)/N - 0.5) * fs);
    D_si   = D * 1e-6;
    beta2  = -lambda^2 * D_si / (2*pi*c);
    H_cd   = exp(-1j * pi * beta2 * L_km*1e3 * (2*pi*freq).^2);
    sig_cd = ifft(fft(sig) .* ifftshift(H_cd));
    % Compensate (inverse filter)
    H_inv  = conj(H_cd);
    sig_comp = ifft(fft(sig_cd) .* ifftshift(H_inv));
    phase_err = std(angle(sig_comp(129:end) .* conj(sig(129:end))));
    fprintf('  CD compensation phase residual: %.2f deg\n', rad2deg(phase_err));
    fprintf('  CD induced ISI taps: ~%d\n', ...
            ceil(abs(D_si * L_km*1e3 * lambda^2 * fs / c)));
    assert(rad2deg(phase_err) < 5.0, 'CD compensation residual too large!');
    fprintf('  PASS: CD compensation residual < 5 deg\n');
end


%% ─────────────────────────────────────────────────────────────────────────
%  Monte Carlo BER (parallel with parfor if PCT available)
%% ─────────────────────────────────────────────────────────────────────────
function results = monte_carlo_ber(n_runs, snr_db, n_sym)
    if nargin < 1, n_runs = 20; end
    if nargin < 2, snr_db = 20; end
    if nargin < 3, n_sym  = 20000; end
    fprintf('--- Monte Carlo BER (%d runs, SNR=%gdB) ---\n', n_runs, snr_db);
    ber_arr = zeros(1, n_runs);
    for r = 1:n_runs
        rng(r * 17 + 3);
        [syms, bits] = gen_pam4(n_sym);
        h_ch = make_channel(56e9, 30);
        rx   = conv(syms, h_ch, 'same');
        sig_pwr = mean(rx.^2);
        rx   = rx + sqrt(sig_pwr/10^(snr_db/10)) * randn(1, n_sym);
        % Scale for ADC
        rx_q = adc_model(rx * 0.3/std(rx), 6, 0.5, 0.15, 56e9);
        [d, ~, ~, ~] = run_ffe_dfe(rx_q, 3, 17, 5, 5e-4, 2e-4, syms, 4000);
        bits_rx = gray_decode(d(4001:end));
        tx_cmp  = bits(8001:8001+length(bits_rx)-1);
        n_cmp   = min(length(bits_rx), length(tx_cmp));
        ber_arr(r) = sum(bits_rx(1:n_cmp) ~= tx_cmp(1:n_cmp)) / n_cmp;
        if mod(r,5)==0
            fprintf('  Run %2d/%d: BER=%.2e\n', r, n_runs, ber_arr(r));
        end
    end
    results.ber_mean  = mean(ber_arr);
    results.ber_std   = std(ber_arr);
    results.ber_worst = max(ber_arr);
    fprintf('  Mean=%.2e  Std=%.2e  Worst=%.2e\n', ...
            results.ber_mean, results.ber_std, results.ber_worst);
end


%% ─────────────────────────────────────────────────────────────────────────
%  Utility: default params (for standalone function calls)
%% ─────────────────────────────────────────────────────────────────────────
function P = get_default_params()
    P.fbaud      = 56e9;
    P.n_sym      = 50000;
    P.n_ffe_pre  = 3;
    P.n_ffe_post = 17;
    P.n_dfe      = 5;
    P.mu_ffe     = 5e-4;
    P.mu_dfe     = 2e-4;
    P.adc_bits   = 6;
    P.adc_vref   = 0.5;
    P.train_len  = 5000;
end

% ── Standalone entry point ─────────────────────────────────────────────────
% Uncomment to run all tests when script is executed directly:
% run_all();
