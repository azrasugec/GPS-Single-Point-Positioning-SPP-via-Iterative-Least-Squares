# -*- coding: utf-8 -*-
"""
GPS Single Point Positioning (SPP) via Least Squares
Azra Sugeç
Station  : ISTA (Istanbul)
Date     : March 16, 2026  (DOY = 075)

Required files (selected via GUI dialogs at run-time):
  1. RINEX Observation file  (.26o or .rnx)
  2. RINEX Navigation file   (.26n)
  3. SP3 Precise Ephemeris   (.SP3)
  4. Ion_Klobuchar.py        (same folder as script, or selected via dialog)
  5. trop_SPPn.py            (same folder as script, or selected via dialog)

IMPORTANT: Do NOT hard-code any file paths.
           The instructor will run this code on a different computer.
"""

# =============================================================================
# 1. IMPORTS
# =============================================================================
import os
import sys
import math
import re
import importlib.util
import warnings
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D   # noqa: F401
from datetime import datetime, timezone

warnings.filterwarnings('ignore')

plt.rcParams.update({
    'figure.dpi': 120,
    'font.size':  11,
    'axes.titlesize': 13,
    'axes.labelsize': 11,
    'legend.fontsize':  9,
    'axes.grid': True,
    'grid.alpha': 0.3,
})

# =============================================================================
# 2. PHYSICAL & WGS84 CONSTANTS
# =============================================================================
c_light = 299_792_458.0       # speed of light              [m/s]
mu      = 3.986005e14         # gravitational constant       [m³/s²]
wE      = 7.2921151467e-5     # Earth rotation rate          [rad/s]
a_wgs   = 6_378_137.0         # WGS84 semi-major axis        [m]
inv_f   = 298.257223563       # WGS84 inverse flattening
f_wgs   = 1.0 / inv_f
e2_wgs  = 2 * f_wgs - f_wgs**2   # first eccentricity squared

# Application date constants
APP_DATE  = datetime(2026, 3, 16, tzinfo=timezone.utc)
GPS_EPOCH = datetime(1980, 1,  6, tzinfo=timezone.utc)
DOY       = APP_DATE.timetuple().tm_yday              # 75
_elapsed  = (APP_DATE - GPS_EPOCH).days
GPS_WEEK  = _elapsed // 7                             # 2410
DOW       = _elapsed % 7                              # 1  (Tuesday)

# Ground-truth ECEF coordinates of ISTA station (IGS SINEX)
GT_X = 4208829.913
GT_Y = 2334850.661
GT_Z = 4171267.446

# =============================================================================
# 3. FILE SELECTION
# =============================================================================

# =============================================================================
# OUTPUT FOLDER SELECTION  (runs once at import / startup)
# =============================================================================
def _choose_output_folder():
    """
    Asks the user to choose a base folder, then creates an 'output' subfolder
    inside it and returns that path.  Falls back to the script directory if the
    dialog is cancelled or tkinter is unavailable.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.lift()
        root.attributes('-topmost', True)
        print('\n[OUTPUT FOLDER]  Select the folder where the "output" directory will be created.')
        print('  (Cancel to save next to this script.)')
        base = filedialog.askdirectory(title='Select Base Folder — an "output" subfolder will be created here')
        root.destroy()
    except Exception:
        base = ''

    if not base:
        try:
            base = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            base = os.getcwd()

    out_dir = os.path.join(base, 'output')
    os.makedirs(out_dir, exist_ok=True)
    print(f'  Output folder: {out_dir}')
    return out_dir


# Call once — result stored in module-level variable used by _out()
OUTPUT_DIR = _choose_output_folder()


def _out(filename):
    """Returns the full path inside OUTPUT_DIR for the given filename."""
    return os.path.join(OUTPUT_DIR, filename)


def _select_file(title, filetypes):
    """
    Opens a Tkinter file-selection dialog.

    Inputs:
        title     : dialog window title (str)
        filetypes : list of (label, glob) tuples

    Output:
        path : absolute path of the selected file (str)
               Raises SystemExit if cancelled.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.lift()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        root.destroy()
        if not path:
            raise SystemExit(f'No file selected for: {title}')
        return path
    except ImportError:
        print(f'\n[FILE REQUIRED]  {title}')
        path = input('  Enter full file path: ').strip()
        if not path or not os.path.isfile(path):
            raise SystemExit(f'File not found: {path}')
        return path


def select_all_files():
    """
    Guides the user through selecting all required input files.
    Ion_Klobuchar.py and trop_SPPn.py are searched in the script folder first.

    Output:
        paths : dict with keys 'obs', 'nav', 'sp3', 'ion', 'trop'
    """
    print('\n' + '=' * 66)
    print('  GMT312 PROJECT – File Selection')
    print('  Please select the required files in the dialogs that open.')
    print('=' * 66)

    paths = {}
    paths['obs'] = _select_file(
        'Select RINEX Observation File (.26o / .rnx)',
        [('RINEX obs', '*.26o *.rnx *.obs'), ('All files', '*.*')])

    paths['nav'] = _select_file(
        'Select RINEX Navigation File (.26n / .rnx)',
        [('RINEX nav', '*.26n *.rnx *.nav'), ('All files', '*.*')])

    paths['sp3'] = _select_file(
        'Select SP3 Precise Ephemeris File (.SP3)',
        [('SP3', '*.SP3 *.sp3'), ('All files', '*.*')])

    # Auto-detect Ion_Klobuchar.py and trop_SPPn.py
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = os.getcwd()

    ion_def  = os.path.join(script_dir, 'Ion_Klobuchar.py')
    trop_def = os.path.join(script_dir, 'trop_SPPn.py')

    if os.path.isfile(ion_def):
        paths['ion'] = ion_def
        print('  Ion_Klobuchar.py found automatically in script folder.')
    else:
        paths['ion'] = _select_file(
            'Select Ion_Klobuchar.py',
            [('Python script', '*.py'), ('All files', '*.*')])

    if os.path.isfile(trop_def):
        paths['trop'] = trop_def
        print('  trop_SPPn.py found automatically in script folder.')
    else:
        paths['trop'] = _select_file(
            'Select trop_SPPn.py',
            [('Python script', '*.py'), ('All files', '*.*')])

    print()
    for key, val in paths.items():
        print(f'  {key:4s} -> {os.path.basename(val)}')
    return paths


def load_module(name, filepath):
    """
    Dynamically imports a Python file as a module.

    Inputs:
        name     : module name (str)
        filepath : absolute path to .py file (str)

    Output:
        module object
    """
    spec   = importlib.util.spec_from_file_location(name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# =============================================================================
# 4. RECEPTION EPOCH COMPUTATION
# =============================================================================

def compute_reception_epoch(student_id_str):
    """
    Computes the assigned reception epoch from the student ID.

    Formula (Project):
        t_raw = (sum of all digits) × 960  [seconds of day]
        If t_raw % 900 == 0  ->  t_rec = t_raw + 810
        Otherwise            ->  t_rec = t_raw

    Inputs:
        student_id_str : student ID (digits only, str)

    Outputs:
        t_rec     : reception epoch in seconds of day (float)
        digit_sum : sum of individual digits (int)
    """
    if not student_id_str.isdigit():
        raise ValueError(f'Student ID must contain digits only: "{student_id_str}"')
    digit_sum = sum(int(d) for d in student_id_str)
    t_raw     = digit_sum * 960
    t_rec     = float(t_raw + 810 if t_raw % 900 == 0 else t_raw)
    return t_rec, digit_sum

# =============================================================================
# 5. RINEX OBSERVATION FILE PARSER
# =============================================================================

def _rinex_version(lines):
    """Returns RINEX version (2 or 3) from the file header."""
    for line in lines[:12]:
        if 'RINEX VERSION' in line:
            try:
                return 3 if float(line[:9].strip()) >= 3.0 else 2
            except ValueError:
                pass
    return 3


def _parse_obs_header(lines):
    """
    Parses the RINEX observation file header.

    Inputs:
        lines : list of raw file lines (list of str)

    Outputs:
        r_apr      : approximate receiver ECEF [X, Y, Z] in metres (numpy array)
        obs_types  : ordered list of GPS observation type codes (list of str)
        header_end : line index after END OF HEADER (int)
        ver        : RINEX version, 2 or 3 (int)
    """
    r_apr      = None
    obs_types  = []
    header_end = 0
    ver        = _rinex_version(lines)
    i          = 0

    while i < len(lines):
        line  = lines[i]
        label = line[60:].strip() if len(line) > 60 else ''

        if 'APPROX POSITION XYZ' in label:
            r_apr = np.array([float(line[0:14]), float(line[14:28]),
                              float(line[28:42])])

        elif ver == 2 and '# / TYPES OF OBSERV' in label:
            n_obs     = int(line[0:6])
            obs_types = line[6:60].split()
            while len(obs_types) < n_obs:
                i += 1
                obs_types += lines[i][6:60].split()
            obs_types = obs_types[:n_obs]

        elif ver == 3 and 'SYS / # / OBS TYPES' in label:
            if line[0] == 'G':
                n_obs     = int(line[1:6])
                obs_types = line[7:60].split()
                while len(obs_types) < n_obs:
                    i += 1
                    obs_types += lines[i][7:60].split()
                obs_types = obs_types[:n_obs]

        elif 'END OF HEADER' in label:
            header_end = i + 1
            break

        i += 1

    return r_apr, obs_types, header_end, ver


def _c1_index(obs_types):
    """
    Returns the index of the C/A pseudorange in the observation type list.
    Priority order: C1C -> C1W -> C1.
    """
    for code in ('C1C', 'C1W', 'C1'):
        if code in obs_types:
            return obs_types.index(code)
    return None


def _parse_rinex2_epochs(lines, start, obs_types, c1_idx):
    """
    Parses RINEX 2 observation epoch records.

    Output:
        epochs : list of dicts {'sod': float, 'sats_ordered': [(prn, C1), ...]}
    """
    epochs = []
    n_obs  = len(obs_types)
    i      = start

    while i < len(lines):
        line = lines[i]
        if (len(line) >= 29 and line[0] == ' '
                and line[1:3].strip().isdigit()
                and line[26:29].strip().isdigit()):
            try:
                sod    = (int(line[10:12]) * 3600
                          + int(line[13:15]) * 60
                          + float(line[15:26]))
                n_sats = int(line[29:32])

                sat_list = []
                sat_line = line
                for k in range(n_sats):
                    if k > 0 and k % 12 == 0:
                        i += 1
                        sat_line = lines[i]
                    col = 32 + (k % 12) * 3
                    prn = sat_line[col:col + 3].strip()
                    sat_list.append(
                        f'G{int(prn):02d}' if prn.isdigit() else prn)

                sats_ordered = []
                for sv in sat_list:
                    obs_vals = []
                    for _ in range(math.ceil(n_obs / 5)):
                        i += 1
                        obs_line = lines[i] if i < len(lines) else ''
                        for k in range(min(5, n_obs - len(obs_vals))):
                            s   = k * 16
                            raw = (obs_line[s:s + 14].strip()
                                   if s + 14 <= len(obs_line) else '')
                            obs_vals.append(float(raw) if raw else 0.0)

                    if sv.startswith('G') and c1_idx is not None:
                        if c1_idx < len(obs_vals) and obs_vals[c1_idx] > 0:
                            sats_ordered.append((sv, obs_vals[c1_idx]))

                epochs.append({'sod': sod, 'sats_ordered': sats_ordered})

            except (ValueError, IndexError):
                pass

        i += 1

    return epochs


def _parse_rinex3_epochs(lines, start, obs_types, c1_idx):
    """
    Parses RINEX 3 observation epoch records.

    Each epoch starts with a '>' record header.  Each satellite observation
    occupies one or more lines:
      - First line  : 3-char system+PRN followed by 16-char observation fields
      - Continuation: additional 16-char fields (no identifier prefix)

    CRITICAL FIX: the number of observations per line varies between RINEX 3
    writers (some use 4, some 13, some put all on one long line).  This parser
    reads continuation lines DYNAMICALLY until n_obs values have been collected,
    instead of using a fixed OBS_PER_LINE constant.

    Each observation field: 14-char value + 2-char flags = 16 chars.
    Blank/missing fields produce float 0.0.

    Inputs / Outputs: same as _parse_rinex2_epochs().
    """
    epochs = []
    n_obs  = len(obs_types)
    i      = start

    while i < len(lines):
        line = lines[i]

        if line.startswith('>'):
            try:
                parts  = line.split()
                sod    = (int(parts[4]) * 3600
                          + int(parts[5]) * 60
                          + float(parts[6]))
                n_sats = int(parts[8])
            except (ValueError, IndexError):
                i += 1
                continue

            sats_ordered = []

            for _ in range(n_sats):
                i += 1
                if i >= len(lines):
                    break

                first_line = lines[i]
                sv         = first_line[0:3].strip()

                # Start collecting raw observation text after the 3-char identifier.
                raw = first_line[3:]

                # Dynamically read continuation lines until we have enough data
                # for n_obs 16-char fields.
                while True:
                    # How many complete 16-char fields does raw contain so far?
                    n_fields = len(raw) // 16
                    if n_fields >= n_obs:
                        break
                    # Peek at the next line
                    next_i = i + 1
                    if next_i >= len(lines):
                        break
                    next_line = lines[next_i]
                    # Stop if next line is a new epoch header
                    if next_line.startswith('>'):
                        break
                    # Stop if next line looks like a satellite identifier line
                    # (letter + 2-digit PRN, e.g. "G01", "R22", "E05")
                    if (len(next_line) >= 3
                            and next_line[0].isalpha()
                            and next_line[1:3].strip().isdigit()):
                        break
                    # It is a continuation line — consume it
                    i += 1
                    raw += next_line

                # Skip non-GPS satellites
                if not sv.startswith('G') or c1_idx is None:
                    continue

                # Parse 16-char observation fields from the concatenated raw string
                obs_vals = []
                pos      = 0
                while len(obs_vals) < n_obs and pos + 14 <= len(raw):
                    val_str = raw[pos:pos + 14].strip()
                    try:
                        obs_vals.append(float(val_str))
                    except ValueError:
                        obs_vals.append(0.0)
                    pos += 16   # 14-char value + 2-char flags

                # Pad with zeros if line ended before all obs types were read
                while len(obs_vals) < n_obs:
                    obs_vals.append(0.0)

                if c1_idx < len(obs_vals) and obs_vals[c1_idx] > 0:
                    sats_ordered.append((sv, obs_vals[c1_idx]))

            epochs.append({'sod': sod, 'sats_ordered': sats_ordered})

        i += 1

    return epochs
def parse_rinex_obs(filepath):
    """
    Reads a RINEX 2 or 3 observation file.

    Inputs:
        filepath : path to observation file (str)

    Outputs:
        r_apr  : approximate receiver ECEF [X, Y, Z] in metres (numpy array)
        epochs : list of epoch dicts
        ver    : RINEX version (int)
    """
    with open(filepath, 'r', errors='replace') as fh:
        lines = fh.readlines()

    r_apr, obs_types, header_end, ver = _parse_obs_header(lines)
    c1_idx = _c1_index(obs_types)

    if ver == 2:
        epochs = _parse_rinex2_epochs(lines, header_end, obs_types, c1_idx)
    else:
        epochs = _parse_rinex3_epochs(lines, header_end, obs_types, c1_idx)

    return r_apr, epochs, ver


def find_epoch_with_min_sats(epochs, t_target, min_sats=5):
    """
    Finds the reception epoch that has at least min_sats GPS satellites
    with valid C/A observations.

    Per the project specification:
      - Search for the epoch closest to t_target.
      - If fewer than 5 GPS satellites are available, add +810 seconds and retry.

    Inputs:
        epochs   : list of epoch dicts from parse_rinex_obs
        t_target : assigned reception epoch in seconds of day (float)
        min_sats : minimum number of required GPS satellites (default 5)

    Outputs:
        epoch  : matched epoch dict
        t_used : seconds-of-day of the matched epoch (float)
    """
    sod_map  = {round(e['sod']): e for e in epochs}
    t_search = t_target
    max_iter = 120   # safety: 120 × 810 s ≈ 27 h

    for step in range(max_iter):
        # Search ±15 s around t_search (RINEX 30-s sampling)
        for offset in (0, 30, -30, 60, -60):
            key = round(t_search + offset)
            if key in sod_map:
                epoch = sod_map[key]
                if len(epoch['sats_ordered']) >= min_sats:
                    if step > 0:
                        print(f'  [NOTE] Insufficient sats at t={t_target:.0f} s. '
                              f'Used t={epoch["sod"]:.0f} s '
                              f'(after {step}x810 s shift).')
                    return epoch, epoch['sod']

        print(f'  [WARNING] Fewer than {min_sats} GPS C/A sats at t={t_search:.0f} s. '
              f'Adding +810 s ...')
        t_search += 810.0

    raise RuntimeError(
        f'Could not find an epoch with ≥{min_sats} GPS C/A satellites '
        f'within 24 h of t={t_target:.0f} s. Check the observation file.')

# =============================================================================
# 6. RINEX NAVIGATION FILE PARSER
# =============================================================================

def parse_nav_header(filepath):
    """
    Reads the RINEX navigation file header and extracts Klobuchar coefficients.

    Supports RINEX 2 (ION ALPHA / ION BETA) and RINEX 3 (GPSA / GPSB).

    Inputs:
        filepath : path to navigation file (str)

    Outputs:
        alpha : list of 4 ION ALPHA values (list of float)
        beta  : list of 4 ION BETA  values (list of float)
    """
    num_pat = re.compile(r'[+-]?\d+\.?\d*[EeDd][+-]\d+|[+-]?\d+\.\d+')
    alpha   = None
    beta    = None

    with open(filepath, 'r', errors='replace') as fh:
        for line in fh:
            label = line[60:].strip() if len(line) > 60 else ''

            if 'ION ALPHA' in label or 'GPSA' in label:
                nums  = num_pat.findall(line[:60])
                alpha = [float(n.replace('D', 'E').replace('d', 'e'))
                         for n in nums[:4]]

            elif 'ION BETA' in label or 'GPSB' in label:
                nums = num_pat.findall(line[:60])
                beta = [float(n.replace('D', 'E').replace('d', 'e'))
                        for n in nums[:4]]

            elif 'END OF HEADER' in label:
                break

    if alpha is None or beta is None:
        raise ValueError(
            'Klobuchar ION ALPHA/BETA coefficients not found in navigation file header.\n'
            f'File: {filepath}')

    return alpha, beta


def _parse_nav_d_exponent(token):
    """Converts a FORTRAN D-exponent string to a Python float."""
    return float(token.replace('D', 'E').replace('d', 'e'))


def _parse_nav_line(line, fields=4, width=19):
    """
    Parses up to `fields` fixed-width values from a navigation data line.
    RINEX navigation uses 19-character fields starting at column 3 (0-indexed).
    """
    vals = []
    start = 3
    for _ in range(fields):
        raw = line[start:start + width].strip() if start + width <= len(line) else ''
        try:
            vals.append(_parse_nav_d_exponent(raw))
        except ValueError:
            vals.append(0.0)
        start += width
    return vals


def parse_nav_data(filepath):
    """
    Parses the body of a RINEX 2 navigation file and returns GPS satellite
    navigation message records including TGD (Total Group Delay).

    Each record contains:
        PRN, epoch (SOD), af0, af1, af2,
        IODE, Crs, delta_n, M0,
        Cuc, e, Cus, sqrt_A,
        t_oe, Cic, OMEGA0, Cis,
        i0, Crc, omega, OMEGA_dot,
        i_dot, codes_on_L2, GPS_week, L2_P,
        SV_acc, SV_health, TGD, IODC

    Inputs:
        filepath : path to RINEX navigation file (str)

    Output:
        nav_records : list of dicts, one per satellite broadcast message
    """
    records = []
    with open(filepath, 'r', errors='replace') as fh:
        lines = fh.readlines()

    # Skip header
    i = 0
    while i < len(lines):
        if 'END OF HEADER' in lines[i][60:]:
            i += 1
            break
        i += 1

    while i < len(lines):
        line = lines[i]

        # RINEX 2 satellite record header: PRN in col 0-1, epoch in cols 3-21
        if len(line) >= 22 and line[0:2].strip().isdigit():
            try:
                prn_num = int(line[0:2].strip())
                prn     = f'G{prn_num:02d}'
                yy  = int(line[3:5].strip())
                mon = int(line[6:8].strip())
                dd  = int(line[9:11].strip())
                hh  = int(line[12:14].strip())
                mi  = int(line[15:17].strip())
                ss  = float(line[17:22].strip())
                sod = hh * 3600 + mi * 60 + ss   # seconds of day

                vals0 = _parse_nav_line(line, fields=3)  # af0, af1, af2
                af0, af1, af2 = vals0[0], vals0[1], vals0[2]

                # Lines 1-7 of navigation record
                rec_vals = []
                for _ in range(7):
                    i += 1
                    if i < len(lines):
                        rec_vals.extend(_parse_nav_line(lines[i], fields=4))
                    else:
                        rec_vals.extend([0.0, 0.0, 0.0, 0.0])

                # RINEX 2 navigation record layout:
                # rec_vals[0-3]  : IODE, Crs, delta_n, M0
                # rec_vals[4-7]  : Cuc, e, Cus, sqrt_A
                # rec_vals[8-11] : t_oe, Cic, OMEGA0, Cis
                # rec_vals[12-15]: i0, Crc, omega, OMEGA_dot
                # rec_vals[16-19]: i_dot, codes_on_L2, GPS_week, L2_P
                # rec_vals[20-23]: SV_acc, SV_health, TGD, IODC
                TGD = rec_vals[22] if len(rec_vals) > 22 else 0.0

                records.append({
                    'prn'      : prn,
                    'sod'      : sod,
                    'af0'      : af0,  'af1': af1,  'af2': af2,
                    'Crs'      : rec_vals[1],
                    'delta_n'  : rec_vals[2],
                    'M0'       : rec_vals[3],
                    'Cuc'      : rec_vals[4],
                    'e'        : rec_vals[5],
                    'Cus'      : rec_vals[6],
                    'sqrt_A'   : rec_vals[7],
                    't_oe'     : rec_vals[8],
                    'Cic'      : rec_vals[9],
                    'OMEGA0'   : rec_vals[10],
                    'Cis'      : rec_vals[11],
                    'i0'       : rec_vals[12],
                    'Crc'      : rec_vals[13],
                    'omega'    : rec_vals[14],
                    'OMEGA_dot': rec_vals[15],
                    'i_dot'    : rec_vals[16],
                    'GPS_week' : rec_vals[18],
                    'TGD'      : TGD,
                })

            except (ValueError, IndexError):
                pass

        i += 1

    return records


def get_nav_record(nav_records, prn, t_target):
    """
    Selects the most appropriate navigation message for a satellite at t_target.
    Chooses the record whose epoch (t_oe) is closest to t_target.

    Inputs:
        nav_records : list of dicts from parse_nav_data
        prn         : satellite PRN string (e.g. 'G05')
        t_target    : target time in seconds of day (float)

    Output:
        record : the best-matching navigation message dict, or None if not found
    """
    candidates = [r for r in nav_records if r['prn'] == prn]
    if not candidates:
        return None
    return min(candidates, key=lambda r: abs(r['t_oe'] - t_target))

# =============================================================================
# 7. SP3 PRECISE EPHEMERIS PARSER
# =============================================================================

def parse_sp3(filepath):
    """
    Reads an SP3-c/d precise ephemeris file.

    Inputs:
        filepath : path to SP3 file (str)

    Output:
        data : dict {PRN: numpy array (N, 5)}
               columns: [sod, X_m, Y_m, Z_m, clk_s]
    """
    data     = {}
    curr_sod = None

    with open(filepath, 'r', errors='replace') as fh:
        for line in fh:
            if line.startswith('*'):
                parts    = line.split()
                curr_sod = (int(parts[4]) * 3600
                            + int(parts[5]) * 60
                            + float(parts[6]))

            elif line.startswith('P') and curr_sod is not None:
                sv = line[1:4].strip()
                if not sv.startswith('G'):
                    continue
                try:
                    x   = float(line[4:18])  * 1e3
                    y   = float(line[18:32]) * 1e3
                    z   = float(line[32:46]) * 1e3
                    raw = line[46:60].strip()
                    clk = (float(raw) * 1e-6
                           if raw and abs(float(raw)) < 999990 else np.nan)
                    data.setdefault(sv, []).append([curr_sod, x, y, z, clk])
                except (ValueError, IndexError):
                    pass

    return {sv: np.array(rows) for sv, rows in data.items()}


def get_sp3_window(sp3_data, sv, t_target, n=10):
    """
    Extracts a symmetric n-epoch window from SP3 data centred on t_target.

    Inputs:
        sp3_data : dict from parse_sp3
        sv       : satellite PRN string (e.g. 'G05')
        t_target : target time in seconds of day (float)
        n        : window size (default 10 for 9th-degree Lagrange)

    Output:
        window : numpy array (n x 5) – [sod, X, Y, Z, clk]
    """
    if sv not in sp3_data:
        raise ValueError(f'Satellite {sv} not found in SP3 file.')
    rows  = sp3_data[sv]
    idx   = int(np.searchsorted(rows[:, 0], t_target))
    half  = n // 2
    start = max(0, idx - half)
    end   = start + n
    if end > len(rows):
        end   = len(rows)
        start = max(0, end - n)
    return rows[start:end]

# =============================================================================
# 8. LAGRANGE INTERPOLATION
# =============================================================================

def lagrange_interp(t_nodes, y_nodes, t):
    """
    9th-degree Lagrange polynomial interpolation over 10 support points.

    Inputs:
        t_nodes : time nodes, length 10 (array-like)
        y_nodes : function values at t_nodes (array-like)
        t       : evaluation point (float)

    Output:
        val : interpolated value (float)
    """
    n   = len(t_nodes)
    val = 0.0
    for j in range(n):
        Lj = 1.0
        for k in range(n):
            if k != j:
                Lj *= (t - t_nodes[k]) / (t_nodes[j] - t_nodes[k])
        val += y_nodes[j] * Lj
    return val


def interp_sp3_xyz(sp3_win, t):
    """
    Interpolates satellite ECEF coordinates from the 10-epoch SP3 window.

    Inputs:
        sp3_win : numpy array (10 x 5) – [sod, X, Y, Z, clk]
        t       : interpolation time in seconds of day (float)

    Output:
        xyz : numpy array [X, Y, Z] in metres
    """
    t_nd = sp3_win[:, 0]
    return np.array([
        lagrange_interp(t_nd, sp3_win[:, 1], t),
        lagrange_interp(t_nd, sp3_win[:, 2], t),
        lagrange_interp(t_nd, sp3_win[:, 3], t),
    ])

# =============================================================================
# 9. SATELLITE POSITION WITH EMISSION TIME AND EARTH ROTATION CORRECTION
# =============================================================================

def R3(theta):
    """
    3x3 rotation matrix about the Z-axis by angle theta [radians].
    Applies the Sagnac (Earth-rotation) correction to satellite ECEF position.

    Inputs:
        theta : rotation angle [radians] (float)

    Output:
        R : 3x3 numpy array
    """
    ct, st = math.cos(theta), math.sin(theta)
    return np.array([[ ct, st, 0.0],
                     [-st, ct, 0.0],
                     [0.0, 0.0, 1.0]])


def emist(trec, pc, clk_win):
    """
    Computes the corrected signal emission time.

    Formula: t_ems = t_rec - P/c - dt_sat

    Inputs:
        trec    : reception time in seconds of day (float)
        pc      : C1 pseudorange [m] (float)
        clk_win : numpy array (10 x 2) – [sod, clock_correction_s]

    Output:
        tems : corrected emission time in seconds of day (float)
    """
    t_nd     = clk_win[:, 0]
    c_nd     = clk_win[:, 1]
    dt_Pc    = pc / c_light
    t_approx = trec - dt_Pc
    dt_sat   = lagrange_interp(t_nd, c_nd, t_approx)
    return trec - dt_Pc - dt_sat


def sat_pos(trec, pc, sp3_win, r_apr):
    """
    Computes the final (Earth-rotation-corrected) ECEF satellite position.

    Steps:
      1. Approximate emission time from pseudorange: t0 = trec - P/c
      2. Iterate twice to refine dt_sat and tems (standard practice):
            dt_sat(k) = SP3_clock(tems(k-1))
            tems(k)   = trec - P/c - dt_sat(k)
      3. Interpolate satellite position at final tems.
      4. Compute travel-time Earth rotation angle theta = wE * (rho/c).
      5. Apply R3(theta) (Sagnac correction).

    Inputs:
        trec    : reception time in seconds of day (float)
        pc      : C1 pseudorange [m] (float)
        sp3_win : numpy array (10 x 5) – [sod, X, Y, Z, clk_s]
        r_apr   : approximate receiver ECEF [X, Y, Z] in metres (array)

    Outputs:
        fpos   : Earth-rotation-corrected satellite ECEF [X, Y, Z] in metres
        dt_sat : satellite clock correction at emission time [s]
        tems   : corrected signal emission time [s]
    """
    clk_win  = sp3_win[:, [0, 4]]
    t_nd     = clk_win[:, 0]
    c_nd     = clk_win[:, 1]

    # Check for NaN clock values – replace with linear interpolation of neighbours
    valid    = ~np.isnan(c_nd)
    if valid.sum() < 2:
        raise ValueError('SP3 clock window has fewer than 2 valid entries.')
    if not valid.all():
        # Replace NaNs with linear interpolation
        c_nd = np.interp(t_nd, t_nd[valid], c_nd[valid])

    # Step 1 – first approximation of emission time (ignores satellite clock)
    dt_Pc    = pc / c_light
    tems     = trec - dt_Pc

    # Step 2 – iterate twice to refine satellite clock and emission time
    for _ in range(2):
        dt_sat = lagrange_interp(t_nd, c_nd, tems)
        tems   = trec - dt_Pc - dt_sat

    # Step 3 – satellite position at corrected emission time
    r_sat_apr = interp_sp3_xyz(sp3_win, tems)

    # Step 4 – Earth rotation correction (Sagnac effect)
    rho     = np.linalg.norm(r_sat_apr - np.asarray(r_apr))
    delta_t = rho / c_light
    theta   = wE * delta_t
    fpos    = R3(theta) @ r_sat_apr

    return fpos, dt_sat, tems

# =============================================================================
# 10. COORDINATE TRANSFORMATION
# =============================================================================

def xyz2plh(cart):
    """
    Converts geocentric Cartesian (ECEF) to geodetic ellipsoidal coordinates.
    Uses iterative Bowring / Heiskanen-Moritz solution.

    Inputs:
        cart : [X, Y, Z] in metres (list or array)

    Outputs:
        phi_deg : geodetic latitude  [degrees]
        lam_deg : geodetic longitude [degrees]
        h       : ellipsoidal height [metres]
    """
    TOL = 1e-12
    X, Y, Z = float(cart[0]), float(cart[1]), float(cart[2])

    p       = math.sqrt(X**2 + Y**2)
    lam     = math.atan2(Y, X)
    phi_old = math.atan2(Z, p * (1.0 - e2_wgs))

    while True:
        N_k     = a_wgs / math.sqrt(1.0 - e2_wgs * math.sin(phi_old)**2)
        phi_new = math.atan2(Z + e2_wgs * N_k * math.sin(phi_old), p)
        if abs(phi_new - phi_old) < TOL:
            break
        phi_old = phi_new

    phi   = phi_new
    N_fin = a_wgs / math.sqrt(1.0 - e2_wgs * math.sin(phi)**2)
    h     = p / math.cos(phi) - N_fin

    return math.degrees(phi), math.degrees(lam), h


def local(rec, sat):
    """
    Computes azimuth, elevation, zenith angle, and slant distance from
    receiver to satellite in the local ENU frame.

    Inputs:
        rec : receiver ECEF [X, Y, Z] in metres
        sat : satellite ECEF [X, Y, Z] in metres

    Outputs:
        az     : azimuth [degrees, 0-360]
        elev   : elevation [degrees]
        zen    : zenith angle [degrees]
        slantd : slant distance [metres]
    """
    Xr, Yr, Zr = float(rec[0]), float(rec[1]), float(rec[2])
    Xs, Ys, Zs = float(sat[0]), float(sat[1]), float(sat[2])

    phi_d, lam_d, _ = xyz2plh(rec)
    phi = math.radians(phi_d)
    lam = math.radians(lam_d)

    dX = Xs - Xr;  dY = Ys - Yr;  dZ = Zs - Zr

    east  = -math.sin(lam) * dX + math.cos(lam) * dY
    north = (-math.sin(phi) * math.cos(lam) * dX
             - math.sin(phi) * math.sin(lam) * dY
             + math.cos(phi) * dZ)
    up    = (math.cos(phi) * math.cos(lam) * dX
             + math.cos(phi) * math.sin(lam) * dY
             + math.sin(phi) * dZ)

    slantd = math.sqrt(east**2 + north**2 + up**2)
    az     = math.degrees(math.atan2(east, north))
    if az < 0.0:
        az += 360.0
    horiz  = math.sqrt(east**2 + north**2)
    elev   = math.degrees(math.atan2(up, horiz))
    zen    = 90.0 - elev

    return az, elev, zen, slantd

# =============================================================================
# 11. ATMOSPHERIC CORRECTION WRAPPERS
# =============================================================================

# Module-level references (set in main after dynamic load)
_Ion_Klobuchar_fn = None
_trop_SPP_fn      = None


def compute_atmospheric_delays(rec, sat_xyz, trec, trecw, alpha, beta, doy, h_m):
    """
    Computes ionospheric and tropospheric delay corrections for one satellite.

    Inputs:
        rec     : receiver ECEF [X, Y, Z] in metres (array)
        sat_xyz : satellite ECEF [X, Y, Z] in metres (array)
        trec    : reception epoch in seconds of day (float)
        trecw   : reception epoch in seconds of GPS week (float)
        alpha   : Klobuchar alpha coefficients (list of 4 floats)
        beta    : Klobuchar beta  coefficients (list of 4 floats)
        doy     : day of year (int)
        h_m     : receiver ellipsoidal height [metres] (float)

    Outputs:
        IonD : ionospheric delay [m]
        TrD  : tropospheric dry slant delay [m]
        TrW  : tropospheric wet slant delay [m]
        az   : azimuth [degrees]
        elev : elevation [degrees]
    """
    phi_deg, lam_deg, _ = xyz2plh(rec)
    az, elev, zen, _ = local(rec, sat_xyz)

    phi_rad  = math.radians(phi_deg)
    lam_rad  = math.radians(lam_deg)
    elev_rad = math.radians(elev)
    az_rad   = math.radians(az)

    IonD = _Ion_Klobuchar_fn(
        phi_rad, lam_rad, elev_rad, az_rad, alpha, beta, trecw)

    Trzd, Trzw, ME = _trop_SPP_fn(phi_deg, doy, h_m, elev_rad)
    TrD = Trzd * ME
    TrW = Trzw * ME

    return IonD, TrD, TrW, az, elev

# =============================================================================
# 12. LEAST SQUARES SPP SOLVER
# =============================================================================


def detect_outlier_satellites(sats_data, r_gt, threshold_m=150.0):
    """
    Identifies satellites whose corrected pseudorange (Lc = C1 + c*dt_sat)
    deviates from the expected value at the known ground-truth position.

    For a correct satellite:
        Lc_i - rho_i(GT) ≈ c * dtr   (constant for all satellites)

    An outlier is a satellite whose Lc - rho(GT) differs from the MEDIAN
    of all satellites by more than `threshold_m` metres.

    This function is used ONLY for debugging and outlier rejection.
    In operational positioning, the ground truth is unknown; here we use it
    to identify and investigate problematic satellites.

    Inputs:
        sats_data   : list of satellite dicts (with 'prn', 'C1', 'dt_sat', 'sat_xyz')
        r_gt        : ground-truth receiver ECEF [X, Y, Z] in metres (array)
        threshold_m : outlier threshold in metres (default 150 m)

    Outputs:
        clean       : list of satellite dicts passing the outlier test
        outliers    : list of (prn, Lc_minus_rhoGT, deviation) for rejected sats
        Lc_rhoGT   : dict {prn: Lc - rho(GT)} for all satellites
    """
    GT = np.asarray(r_gt)
    Lc_rhoGT = {}

    for sd in sats_data:
        sat_xyz = np.asarray(sd['sat_xyz'])
        rho_gt  = np.linalg.norm(sat_xyz - GT)
        Lc_i    = sd['C1'] + c_light * sd['dt_sat']
        Lc_rhoGT[sd['prn']] = Lc_i - rho_gt

    values  = list(Lc_rhoGT.values())
    median  = float(np.median(values))

    clean    = []
    outliers = []
    for sd in sats_data:
        prn       = sd['prn']
        val       = Lc_rhoGT[prn]
        deviation = val - median
        if abs(deviation) > threshold_m:
            outliers.append((prn, val, deviation))
        else:
            clean.append(sd)

    return clean, outliers, Lc_rhoGT, median


def spp_least_squares(sats_data, apply_corrections=False,
                      trec=None, trecw=None,
                      alpha=None, beta=None, doy=None,
                      nav_records=None,
                      r_apr_for_atmos=None,
                      elev_mask_deg=0.0,
                      verbose=True):
    """
    Iterative Least Squares Single Point Positioning (SPP).

    Observation model:
        P_i = rho_i + c*dtr - c*dts_i + I_i + T_i + TGD_i

    Corrected observation (moved to right-hand side):
        Lc_i = P_i + c*dts_i                       (Case 1)
        Lc_i = P_i + c*dts_i - I_i - T_i - TGD_i  (Case 2)

    Linearised around X0, dtr0:
        Lc_i - rho(X0) - c*dtr0 = -ex*dX - ey*dY - ez*dZ + c*d(dtr)

    Design matrix row: A_i = [-ex, -ey, -ez, +1]
    Unknowns:          u   = [dX,  dY,  dZ,  c*dtr]

    Starting point: X0 = [0, 0, 0], dtr0 = 0  (as required by project spec)
    Convergence:    |dX|, |dY|, |dZ| < 1 mm

    Atmospheric corrections are computed ONCE at r_apr_for_atmos (RINEX header
    approximate position) before iteration begins. Satellites below elev_mask_deg
    are excluded.

    Inputs:
        sats_data         : list of dicts – 'prn', 'C1', 'sat_xyz', 'dt_sat', 'TGD'
        apply_corrections : if True, apply Iono + Trop + TGD (bool)
        trec              : reception time [s of day]       (float)
        trecw             : reception time [s of GPS week]  (float)
        alpha, beta       : Klobuchar coefficients          (list of 4 floats)
        doy               : day of year                     (int)
        nav_records       : navigation records list
        r_apr_for_atmos   : approximate receiver ECEF [m]   (array, required if corrections)
        elev_mask_deg     : elevation cutoff angle [degrees] (default 0 = no mask)
        verbose           : print diagnostic table           (bool)

    Outputs:
        X_est        : final receiver ECEF [X, Y, Z] in metres (array)
        dt_r         : receiver clock bias [s] (float)
        iterations   : iteration list of dicts
        residuals    : final residual vector [m] (array)
        sat_geometry : per-satellite geometry and correction list
    """
    # ------------------------------------------------------------------
    # Step A: elevation pre-filter using r_apr_for_atmos (or r_apr of header).
    # We need an approximate position to compute elevations BEFORE iteration.
    # Use r_apr_for_atmos if available; otherwise skip elevation filtering.
    # ------------------------------------------------------------------
    ref_pos = r_apr_for_atmos if r_apr_for_atmos is not None else None

    filtered_sats = []
    excluded_sats = []
    for sd in sats_data:
        if ref_pos is not None and elev_mask_deg > 0:
            az_pre, elev_pre, _, _ = local(ref_pos, np.asarray(sd['sat_xyz']))
            sd = dict(sd)           # shallow copy to avoid mutating original
            sd['elev_pre'] = elev_pre
            if elev_pre < elev_mask_deg:
                excluded_sats.append((sd['prn'], elev_pre))
                continue
        filtered_sats.append(sd)

    if excluded_sats and verbose:
        for prn_ex, el_ex in excluded_sats:
            print(f'  [MASK] {prn_ex} excluded: elevation = {el_ex:.2f}° < {elev_mask_deg:.0f}°')

    if len(filtered_sats) < 4:
        raise RuntimeError(
            f'After elevation mask ({elev_mask_deg}°), only {len(filtered_sats)} '
            f'satellites remain. Need at least 4.')

    sats = filtered_sats

    # ------------------------------------------------------------------
    # Step B: Pre-compute atmospheric corrections once at r_apr_for_atmos.
    # Standard SPP practice: fix corrections for all iterations.
    # ------------------------------------------------------------------
    atmos_corr = {}

    if apply_corrections:
        if r_apr_for_atmos is None:
            raise ValueError('r_apr_for_atmos must be supplied when apply_corrections=True')
        phi_deg_a, lam_deg_a, h_m_a = xyz2plh(r_apr_for_atmos)
        if verbose:
            print('  Pre-computing atmospheric corrections at RINEX header position:')
        for sd in sats:
            sat_xyz = np.asarray(sd['sat_xyz'])
            try:
                IonD_i, TrD_i, TrW_i, az_i, elev_i = compute_atmospheric_delays(
                    r_apr_for_atmos, sat_xyz,
                    trec, trecw, alpha, beta, doy, h_m_a)
            except Exception as exc:
                if verbose:
                    print(f'    [WARN] Atmos. failed for {sd["prn"]}: {exc}. Using 0.')
                IonD_i = TrD_i = TrW_i = az_i = elev_i = 0.0

            # TGD: from navigation file, convert seconds -> metres
            TGD_m_i = sd.get('TGD', 0.0) * c_light

            atmos_corr[sd['prn']] = (IonD_i, TrD_i, TrW_i, TGD_m_i, az_i, elev_i)

            if verbose:
                print(f'    {sd["prn"]:>5}: El={elev_i:6.2f}°  '
                      f'Ion={IonD_i:7.3f} m  '
                      f'Trop={TrD_i+TrW_i:7.3f} m  '
                      f'TGD={TGD_m_i:7.3f} m')

    # ------------------------------------------------------------------
    # Step C: Compute corrected observations Lc_i.
    #
    # Full pseudorange model:
    #   P_i = rho_i + c*dtr - c*dts_i + I_i + T_i + TGD_i
    #
    # Rearranged (satellite clock and atmospheric terms moved to left side):
    #   Lc_i = P_i + c*dts_i - I_i - T_i - TGD_i = rho_i + c*dtr
    #
    # Note on signs:
    #   +c*dts_i  : SP3 satellite clock correction subtracted from measurement
    #               (dts_i positive => satellite ahead => P too large => reduce P)
    #               Actually: P = rho + c*(dtr - dts) => Lc = P + c*dts ✓
    #   -I_i      : ionosphere adds to path length; correct by subtracting
    #   -T_i      : troposphere adds to path length; correct by subtracting
    #   -TGD_i    : total group delay adds to path length; correct by subtracting
    # ------------------------------------------------------------------
    Lc = {}
    for sd in sats:
        C1     = sd['C1']
        dt_sat = sd['dt_sat']   # satellite clock correction [s], from SP3

        # Remove satellite clock error: Lc = P + c*dt_sat
        # SP3: P = rho + c*(dtr - dts)  =>  Lc = P + c*dts = P + c*dt_sat
        Lc_i = C1 + c_light * dt_sat

        if apply_corrections:
            IonD_i, TrD_i, TrW_i, TGD_m_i, az_i, elev_i = atmos_corr[sd['prn']]
            # Subtract all additive delays
            Lc_i -= (IonD_i + TrD_i + TrW_i + TGD_m_i)

        Lc[sd['prn']] = Lc_i

    # ------------------------------------------------------------------
    # Step D: Diagnostic table – compare Lc with rho from ground truth.
    # Ideally: Lc_i - rho(GT)_i ≈ constant = c*dtr for all satellites.
    # A satellite deviating by more than ~100 m is suspicious.
    # ------------------------------------------------------------------
    if verbose:
        GT_pos = np.array([GT_X, GT_Y, GT_Z])
        print(f'\n  {"PRN":>5}  {"C1 [m]":>14}  {"c·dts [m]":>11}  '
              f'{"rho(GT) [m]":>14}  {"Lc−rho(GT) [m]":>16}  {"el [°]":>7}')
        print('  ' + '-' * 78)
        for sd in sats:
            sat_xyz = np.asarray(sd['sat_xyz'])
            rho_gt  = np.linalg.norm(sat_xyz - GT_pos)
            Lc_i    = Lc[sd['prn']]
            cdt_s   = c_light * sd['dt_sat']
            # Elevation using GT position
            _, elev_gt, _, _ = local(GT_pos, sat_xyz)
            print(f'  {sd["prn"]:>5}  {sd["C1"]:>14.3f}  {cdt_s:>11.3f}  '
                  f'{rho_gt:>14.3f}  {Lc_i - rho_gt:>16.3f}  {elev_gt:>7.2f}')
        print('  (Lc − rho(GT) should be nearly constant ≈ c·dtr for all sats)')

    # ------------------------------------------------------------------
    # Step E: Iterative Least Squares
    # ------------------------------------------------------------------
    rec_pos    = np.array([0.0, 0.0, 0.0])
    cdt_r      = 0.0
    iterations = []
    MAX_ITER   = 50
    TOL_mm     = 1e-3   # 1 mm

    for it in range(1, MAX_ITER + 1):
        A_rows = []
        l_rows = []

        for sd in sats:
            sat_xyz = np.asarray(sd['sat_xyz'])
            diff    = sat_xyz - rec_pos
            rho     = np.linalg.norm(diff)

            # Guard for degenerate first iteration (rec at origin, rho ≈ 20-27 Mm)
            # No guard needed: rho will be very large but numerically stable.

            e_vec   = diff / rho
            l_i     = Lc[sd['prn']] - rho - cdt_r

            # Design matrix: A_i = [-ex, -ey, -ez, +1]
            A_rows.append([-e_vec[0], -e_vec[1], -e_vec[2], 1.0])
            l_rows.append(l_i)

        A  = np.array(A_rows)
        l  = np.array(l_rows)

        try:
            dx = np.linalg.solve(A.T @ A, A.T @ l)
        except np.linalg.LinAlgError:
            raise RuntimeError('Singular design matrix – insufficient satellite geometry.')

        dX, dY, dZ, d_cdt = dx
        rec_pos[0] += dX
        rec_pos[1] += dY
        rec_pos[2] += dZ
        cdt_r      += d_cdt

        iterations.append({
            'iter' : it,
            'dX'   : dX,   'dY'  : dY,   'dZ'  : dZ,
            'cdt_r': d_cdt,
            'X'    : rec_pos[0],
            'Y'    : rec_pos[1],
            'Z'    : rec_pos[2],
        })

        if abs(dX) < TOL_mm and abs(dY) < TOL_mm and abs(dZ) < TOL_mm:
            break

    # ------------------------------------------------------------------
    # Step F: Final residuals and satellite geometry
    # ------------------------------------------------------------------
    residuals    = []
    sat_geometry = []

    for sd in sats:
        sat_xyz = np.asarray(sd['sat_xyz'])
        rho     = np.linalg.norm(sat_xyz - rec_pos)
        v_i     = Lc[sd['prn']] - rho - cdt_r
        residuals.append(v_i)

        az_f, elev_f, _, _ = local(rec_pos, sat_xyz)

        if apply_corrections:
            IonD_i, TrD_i, TrW_i, TGD_m_i, az_i, elev_i = atmos_corr[sd['prn']]
        else:
            IonD_i = TrD_i = TrW_i = TGD_m_i = 0.0

        sat_geometry.append({
            'prn'  : sd['prn'],
            'az'   : az_f,
            'elev' : elev_f,
            'C1'   : sd['C1'],
            'IonD' : IonD_i,
            'TrD'  : TrD_i,
            'TrW'  : TrW_i,
            'TGD_m': TGD_m_i,
        })

    residuals = np.array(residuals)
    dt_r      = cdt_r / c_light   # metres -> seconds

    return rec_pos.copy(), dt_r, iterations, residuals, sat_geometry


# =============================================================================
# 13. PRINTING / REPORTING HELPERS
# =============================================================================

def print_section(title, char='=', width=72):
    """Prints a formatted section header."""
    line = char * width
    print(f'\n{line}')
    print(f'  {title}')
    print(line)


def print_iteration_table(iterations):
    """
    Prints the iteration convergence table.

    Inputs:
        iterations : list of iteration dicts from spp_least_squares
    """
    hdr = (f"{'Iter':>5}  {'dX [mm]':>12}  {'dY [mm]':>12}  {'dZ [mm]':>12}  "
           f"{'c·dtr [m]':>12}  {'X [m]':>14}  {'Y [m]':>14}  {'Z [m]':>14}")
    print(hdr)
    print('-' * len(hdr))
    for it in iterations:
        print(f"{it['iter']:>5}  "
              f"{it['dX']*1e3:>12.4f}  "
              f"{it['dY']*1e3:>12.4f}  "
              f"{it['dZ']*1e3:>12.4f}  "
              f"{it['cdt_r']:>12.4f}  "
              f"{it['X']:>14.4f}  "
              f"{it['Y']:>14.4f}  "
              f"{it['Z']:>14.4f}")


def print_satellite_table(sat_geometry):
    """
    Prints per-satellite information table.

    Inputs:
        sat_geometry : list of dicts from spp_least_squares
    """
    hdr = (f"{'PRN':>5}  {'Elev [°]':>10}  {'Az [°]':>10}  {'C1 [m]':>14}  "
           f"{'IonD [m]':>10}  {'TrD+TrW [m]':>12}  {'TGD [m]':>10}")
    print(hdr)
    print('-' * len(hdr))
    for sg in sat_geometry:
        print(f"{sg['prn']:>5}  "
              f"{sg['elev']:>10.3f}  "
              f"{sg['az']:>10.3f}  "
              f"{sg['C1']:>14.3f}  "
              f"{sg['IonD']:>10.4f}  "
              f"{sg['TrD']+sg['TrW']:>12.4f}  "
              f"{sg['TGD_m']:>10.4f}")


def print_residual_analysis(residuals, label=''):
    """
    Prints residual statistics.

    Inputs:
        residuals : numpy array of residual values [m]
        label     : optional label string
    """
    rms  = np.sqrt(np.mean(residuals**2))
    mean = np.mean(residuals)
    vmax = np.max(np.abs(residuals))
    print(f'  {"Case":<20}: {label}')
    print(f'  {"RMS residual":<20}: {rms:.4f} m')
    print(f'  {"Mean residual":<20}: {mean:.4f} m')
    print(f'  {"Max |residual|":<20}: {vmax:.4f} m')


def print_accuracy_comparison(X, Y, Z, label=''):
    """
    Prints coordinate errors vs. ISTA ground truth.

    Inputs:
        X, Y, Z : estimated ECEF coordinates [m] (float)
        label   : case description
    """
    dX   = X - GT_X
    dY   = Y - GT_Y
    dZ   = Z - GT_Z
    err3 = math.sqrt(dX**2 + dY**2 + dZ**2)
    print(f'\n  {label}')
    print(f'  {"Estimated X":>18}: {X:>18.3f} m   (error: {dX:+.3f} m)')
    print(f'  {"Estimated Y":>18}: {Y:>18.3f} m   (error: {dY:+.3f} m)')
    print(f'  {"Estimated Z":>18}: {Z:>18.3f} m   (error: {dZ:+.3f} m)')
    print(f'  {"3D error":>18}: {err3:>18.4f} m')

# =============================================================================
# 14. SKYPLOT
# =============================================================================

def plot_skyplot(sat_geometry, title='Sky Plot – All Used GPS Satellites',
                 out_path=_out('skyplot_project.png')):
    """
    Creates a polar sky plot for all used GPS satellites.

    Inputs:
        sat_geometry : list of dicts with 'prn', 'az', 'elev'
        title        : plot title (str)
        out_path     : output PNG filename (str)
    """
    colors = plt.cm.tab20(np.linspace(0, 1, len(sat_geometry)))

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw={'projection': 'polar'})
    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)

    for sg, col in zip(sat_geometry, colors):
        if sg['elev'] <= 0:
            continue
        r      = 90.0 - sg['elev']
        az_rad = math.radians(sg['az'])
        ax.plot(az_rad, r, 'o', markersize=12, color=col, label=sg['prn'], zorder=5)
        ax.annotate(f"  {sg['prn']}", xy=(az_rad, r), fontsize=8, color=col)

    ax.set_rticks([0, 15, 30, 45, 60, 75, 90])
    ax.set_yticklabels(['90°', '75°', '60°', '45°', '30°', '15°', '0°'], fontsize=8)
    ax.set_rlabel_position(45)
    ax.set_title(title, fontsize=12, pad=18)
    ax.legend(loc='upper right', bbox_to_anchor=(1.35, 1.12), fontsize=8)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  Saved: {out_path}')


def plot_convergence(iterations_case1, iterations_case2,
                     out_path='convergence_project.png'):
    """
    Plots the iteration convergence (|dX|, |dY|, |dZ| in mm) for both cases.

    Inputs:
        iterations_case1 : iteration list from Case 1
        iterations_case2 : iteration list from Case 2
        out_path         : output PNG filename (str)
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle('Least Squares Iteration Convergence', fontsize=13, fontweight='bold')

    for ax, iters, label, color in [
            (axes[0], iterations_case1, 'Case 1 (No corrections)', '#1565C0'),
            (axes[1], iterations_case2, 'Case 2 (With corrections)', '#B71C1C')]:
        xs  = [it['iter'] for it in iters]
        dXs = [abs(it['dX']) * 1e3 for it in iters]
        dYs = [abs(it['dY']) * 1e3 for it in iters]
        dZs = [abs(it['dZ']) * 1e3 for it in iters]

        ax.semilogy(xs, dXs, 'o-', color='#1565C0', label='|dX|')
        ax.semilogy(xs, dYs, 's-', color='#2E7D32', label='|dY|')
        ax.semilogy(xs, dZs, '^-', color='#B71C1C', label='|dZ|')
        ax.axhline(1.0, color='gray', linestyle='--', linewidth=1.2, label='1 mm threshold')

        ax.set_xlabel('Iteration')
        ax.set_ylabel('|dX|, |dY|, |dZ| [mm]')
        ax.set_title(label)
        ax.legend(fontsize=9)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  Saved: {out_path}')


def plot_correction_contributions(sg_case2, out_path=_out('corrections_project.png')):
    """
    Bar chart of ionosphere, troposphere and TGD contribution per satellite.

    Inputs:
        sg_case2 : sat_geometry list from Case 2
        out_path : output PNG filename (str)
    """
    prns  = [s['prn']  for s in sg_case2]
    ions  = [s['IonD'] for s in sg_case2]
    trops = [s['TrD'] + s['TrW'] for s in sg_case2]
    tgds  = [s['TGD_m'] for s in sg_case2]

    x    = np.arange(len(prns))
    w    = 0.28

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(x - w,   ions,  w, label='Ionosphere (IonD)',    color='#E53935')
    ax.bar(x,       trops, w, label='Troposphere (TrD+TrW)', color='#1E88E5')
    ax.bar(x + w,   tgds,  w, label='TGD [m]',              color='#43A047')

    ax.set_xticks(x)
    ax.set_xticklabels(prns)
    ax.set_ylabel('Correction [m]')
    ax.set_title('Per-Satellite Correction Contributions (Case 2)')
    ax.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  Saved: {out_path}')


def plot_residuals(residuals1, residuals2, sats1, sats2,
                   out_path=_out('residuals_project.png')):
    """
    Bar chart of final residuals for both cases.

    Inputs:
        residuals1 : residual array from Case 1
        residuals2 : residual array from Case 2
        sats1      : sat_geometry list from Case 1
        sats2      : sat_geometry list from Case 2
        out_path   : output PNG filename (str)
    """
    prns1 = [s['prn'] for s in sats1]
    prns2 = [s['prn'] for s in sats2]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle('Final Observation Residuals', fontsize=13, fontweight='bold')

    for ax, res, prns, label, color in [
            (axes[0], residuals1, prns1, 'Case 1 (No corrections)', '#1565C0'),
            (axes[1], residuals2, prns2, 'Case 2 (With corrections)', '#B71C1C')]:
        ax.bar(prns, res, color=color, edgecolor='black', linewidth=0.8)
        ax.axhline(0, color='black', linewidth=0.8)
        ax.set_ylabel('Residual [m]')
        rms = np.sqrt(np.mean(res**2))
        ax.set_title(f'{label}\nRMS = {rms:.4f} m')

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  Saved: {out_path}')


def plot_earth_rotation_comparison(rec1_no_rot, rec1_with_rot,
                                   out_path=_out('earth_rotation_project.png')):
    """
    Bar chart comparing coordinate components with and without Earth rotation correction.

    Inputs:
        rec1_no_rot   : receiver ECEF [X,Y,Z] without Earth rotation (array)
        rec1_with_rot : receiver ECEF [X,Y,Z] with Earth rotation (array)
        out_path      : output PNG filename (str)
    """
    diff  = rec1_with_rot - rec1_no_rot
    comps = ['ΔX', 'ΔY', 'ΔZ']
    colors = ['#1565C0', '#2E7D32', '#B71C1C']

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(comps, diff, color=colors, edgecolor='black', linewidth=0.8)
    ax.axhline(0, color='black', linewidth=0.8)
    for bar, val in zip(bars, diff):
        sign = np.sign(val) if val != 0 else 1
        ax.text(bar.get_x() + bar.get_width() / 2,
                val + sign * max(abs(diff)) * 0.05,
                f'{val:.4f} m', ha='center', fontsize=10, fontweight='bold')
    ax.set_ylabel('Coordinate Difference [m]')
    ax.set_title('Effect of Earth Rotation Correction on Receiver Position\n'
                 '(Case 1: with correction − without correction)')
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  Saved: {out_path}')

# =============================================================================
# 15. MAIN PROGRAM
# =============================================================================

def main():
    """
    Entry point for the GMT312 GPS SPP project.

    Pipeline:
      A. Student ID  -> reception epoch
      B. File selection (obs, nav, sp3, Ion_Klobuchar.py, trop_SPPn.py)
      C. Parse all input files
      D. Find target epoch with ≥ 5 GPS satellites
      E. Compute satellite positions (SP3 + Lagrange + Earth rotation)
      F. Case 1: Least Squares WITHOUT corrections
      G. Case 2: Least Squares WITH corrections (Iono + Trop + TGD)
      H. Earth rotation comparison
      I. Print all results
      J. Save all figures
    """
    global _Ion_Klobuchar_fn, _trop_SPP_fn

    print('\n' + '=' * 72)
    print('  GMT312 – GPS Single Point Positioning (SPP)')
    print('  Semester Project – March 16, 2026  |  Station: ISTA')
    print('=' * 72)



    # ------------------------------------------------------------------
    # A. Student ID -> reception epoch
    # ------------------------------------------------------------------
    student_id       = input('\nEnter your Student ID (digits only): ').strip()
    t_rec, digit_sum = compute_reception_epoch(student_id)
    trecw            = DOW * 86400.0 + t_rec   # seconds of GPS week

    h_disp  = int(t_rec // 3600)
    mi_disp = int((t_rec % 3600) // 60)
    ss_disp = t_rec % 60

    print(f'\n  Student ID  : {student_id}')
    print(f'  Digit sum   : {" + ".join(student_id)} = {digit_sum}')
    print(f'  t_raw       : {digit_sum} × 960 = {digit_sum * 960} s')
    if digit_sum * 960 != t_rec:
        print(f'  +810 s applied (multiple of 900)  ->  t_rec = {t_rec:.0f} s')
    print(f'  t_rec       : {t_rec:.0f} s  ({h_disp:02d}:{mi_disp:02d}:{ss_disp:04.1f} UTC)')
    print(f'  t_rec (GPS week): {trecw:.0f} s   |   GPS Week {GPS_WEEK} / DOW {DOW}')
    print(f'  DOY         : {DOY}  (March 16, 2026)')

    # ------------------------------------------------------------------
    # B. File selection
    # ------------------------------------------------------------------
    paths = select_all_files()

    # ------------------------------------------------------------------
    # C. Load atmospheric correction modules
    # ------------------------------------------------------------------
    print('\nLoading atmospheric correction modules ...')
    _Ion_Klobuchar_fn = load_module('Ion_Klobuchar', paths['ion']).Ion_Klobuchar
    _trop_SPP_fn      = load_module('trop_SPPn',     paths['trop']).trop_SPP
    print('  Ion_Klobuchar : OK')
    print('  trop_SPP      : OK')

    # ------------------------------------------------------------------
    # D. Parse RINEX navigation file (TGD + Klobuchar coefficients)
    # ------------------------------------------------------------------
    print('\nParsing RINEX navigation file ...')
    alpha, beta  = parse_nav_header(paths['nav'])
    nav_records  = parse_nav_data(paths['nav'])
    print(f'  ION ALPHA : {[f"{v:.4e}" for v in alpha]}')
    print(f'  ION BETA  : {[f"{v:.4e}" for v in beta]}')
    print(f'  Navigation records: {len(nav_records)}')

    # ------------------------------------------------------------------
    # E. Parse RINEX observation file
    # ------------------------------------------------------------------
    print('\nParsing RINEX observation file ...')
    r_apr, epochs, ver = parse_rinex_obs(paths['obs'])
    print(f'  RINEX version : {ver}')
    print(f'  Total epochs  : {len(epochs)}')
    print(f'  Approx. receiver ECEF (from header):')
    print(f'    X = {r_apr[0]:>18.3f} m')
    print(f'    Y = {r_apr[1]:>18.3f} m')
    print(f'    Z = {r_apr[2]:>18.3f} m')

    # ------------------------------------------------------------------
    # F. Find the target epoch with ≥ 5 GPS satellites
    # ------------------------------------------------------------------
    print(f'\nSearching for epoch {t_rec:.0f} s with ≥5 GPS C/A satellites ...')
    epoch, t_ep = find_epoch_with_min_sats(epochs, t_rec, min_sats=5)
    ep_h  = int(t_ep // 3600)
    ep_mi = int((t_ep % 3600) // 60)
    ep_ss = t_ep % 60
    print(f'  Used epoch : {t_ep:.0f} s  ({ep_h:02d}:{ep_mi:02d}:{ep_ss:04.1f} UTC)')
    trecw_used = DOW * 86400.0 + t_ep

    gps_sats = epoch['sats_ordered']
    print(f'\n  GPS satellites at epoch {t_ep:.0f} s ({len(gps_sats)} total):')
    for sv, c1v in gps_sats:
        print(f'    {sv}: C1 = {c1v:.3f} m')

    # ------------------------------------------------------------------
    # G. Parse SP3 and compute satellite positions
    # ------------------------------------------------------------------
    print('\nParsing SP3 precise ephemeris file ...')
    sp3_data = parse_sp3(paths['sp3'])
    print(f'  GPS satellites : {sorted(sp3_data.keys())}')

    print('\nComputing satellite positions (SP3 + Lagrange + Earth rotation) ...')
    print(f'  {"PRN":>5}  {"C1 [m]":>14}  {"dt_sat [µs]":>12}  '
          f'{"NaN clks":>9}  {"TGD [ns]":>10}  {"Status"}')
    print('  ' + '-' * 72)
    sats_data = []
    for sv, C1 in gps_sats:
        if sv not in sp3_data:
            print(f'  {sv:>5}  {"—":>14}  {"—":>12}  {"—":>9}  {"—":>10}  SKIP: not in SP3')
            continue

        sp3_win = get_sp3_window(sp3_data, sv, t_ep)
        n_nan   = int(np.sum(np.isnan(sp3_win[:, 4])))

        if n_nan == len(sp3_win):
            print(f'  {sv:>5}  {C1:>14.3f}  {"—":>12}  {n_nan:>9}  {"—":>10}  SKIP: all SP3 clocks NaN')
            continue

        try:
            fpos, dt_sat, tems = sat_pos(t_ep, C1, sp3_win, r_apr)
        except Exception as exc:
            print(f'  {sv:>5}  {C1:>14.3f}  {"ERR":>12}  {n_nan:>9}  {"—":>10}  SKIP: {exc}')
            continue

        # Sanity check: dt_sat should be small (< ±1 ms for GPS)
        dt_sat_us = dt_sat * 1e6
        dt_warn   = ' *** LARGE dt_sat!' if abs(dt_sat_us) > 1000 else ''

        nav_rec = get_nav_record(nav_records, sv, t_ep)
        TGD_s   = nav_rec['TGD'] if nav_rec is not None else 0.0

        sats_data.append({
            'prn'     : sv,
            'C1'      : C1,
            'sat_xyz' : fpos,
            'dt_sat'  : dt_sat,
            'TGD'     : TGD_s,
            'sp3_win' : sp3_win,
            'tems'    : tems,
            'n_nan_clk': n_nan,
        })
        print(f'  {sv:>5}  {C1:>14.3f}  {dt_sat_us:>12.4f}  '
              f'{n_nan:>9}  {TGD_s*1e9:>10.2f}  OK{dt_warn}')

    if len(sats_data) < 4:
        raise RuntimeError(
            f'Only {len(sats_data)} satellites available in SP3. Need at least 4.')

    # ------------------------------------------------------------------
    # H. THREE-SCENARIO ANALYSIS
    #    Scenario A: All satellites, no elevation mask
    #    Scenario B: Elevation mask only (10°)
    #    Scenario C: Outlier-rejected (Lc−rho(GT) based, threshold 150 m)
    # ------------------------------------------------------------------
    ELEV_MASK    = 10.0    # degrees
    OUTLIER_THRS = 150.0   # metres

    GT_pos = np.array([GT_X, GT_Y, GT_Z])

    # ── Outlier detection (uses ground truth — for debugging/report only) ──
    print_section('OUTLIER DETECTION (using ground-truth position for diagnosis)')
    clean_sats, outlier_list, Lc_rhoGT_all, median_val = detect_outlier_satellites(
        sats_data, GT_pos, threshold_m=OUTLIER_THRS)

    print(f'\n  {"PRN":>5}  {"Lc−rho(GT) [m]":>16}  {"Deviation [m]":>14}  Status')
    print('  ' + '-' * 52)
    for sd in sats_data:
        prn = sd['prn']
        val = Lc_rhoGT_all[prn]
        dev = val - median_val
        status = 'OUTLIER ← rejected' if abs(dev) > OUTLIER_THRS else 'OK'
        # Get pre-computed elevation if available
        az_d, elev_d, _, _ = local(r_apr, np.asarray(sd['sat_xyz']))
        print(f'  {prn:>5}  {val:>16.3f}  {dev:>14.3f}  {status}  (el={elev_d:.1f}°)')
    print(f'\n  Median Lc−rho(GT) : {median_val:.3f} m  (≈ c · dtr_receiver)')
    print(f'  Threshold         : ±{OUTLIER_THRS:.0f} m')
    print(f'  Rejected sats     : {[o[0] for o in outlier_list]}')
    print(f'  Retained sats     : {[s["prn"] for s in clean_sats]}')

    if outlier_list:
        print('\n  Investigation of rejected satellites:')
        for prn_out, val_out, dev_out in outlier_list:
            sd_out = next(s for s in sats_data if s['prn'] == prn_out)
            az_o, elev_o, _, _ = local(r_apr, np.asarray(sd_out['sat_xyz']))
            n_nan = sd_out.get('n_nan_clk', '?')
            print(f'    {prn_out}: Lc−rho(GT)={val_out:.1f} m  dev={dev_out:+.1f} m  '
                  f'el={elev_o:.1f}°  dt_sat={sd_out["dt_sat"]*1e6:.3f} µs  '
                  f'NaN clks={n_nan}  C1={sd_out["C1"]:.3f} m')
            if n_nan and n_nan > 0:
                print(f'      → Likely cause: {n_nan} NaN SP3 clock(s) in window → '
                      f'interpolation degraded')
            if elev_o < 5:
                print(f'      → Very low elevation ({elev_o:.1f}°): '
                      f'severe multipath and atmosphere contamination')
            if abs(dev_out) > 1000:
                print(f'      → Deviation {abs(dev_out):.0f} m >> {OUTLIER_THRS:.0f} m: '
                      f'likely SP3 clock NaN → dt_sat≈0 → Lc off by c·true_dts')

    # ── Helper to run and print one complete SPP scenario ──
    def _run_and_print(label, sat_list, case2=False, mask=0.0):
        """Runs SPP for one scenario, prints full results, returns (X, dtr, iters, res, sg)."""
        print_section(label)
        args = dict(
            sats_data        = sat_list,
            apply_corrections= case2,
            r_apr_for_atmos  = r_apr,
            elev_mask_deg    = mask,
            verbose          = True,
        )
        if case2:
            args.update(trec=t_ep, trecw=trecw_used,
                        alpha=alpha, beta=beta, doy=DOY, nav_records=nav_records)
        X, dtr, iters, res, sg = spp_least_squares(**args)
        print(f'\n  Iterations: {len(iters)}')
        print('\n  Iteration Convergence Table:')
        print_iteration_table(iters)
        print('\n  Satellite Information:')
        print_satellite_table(sg)
        print('\n  Residual Analysis:')
        tag = ('Case 2' if case2 else 'Case 1') + f' – {label}'
        print_residual_analysis(res, tag)
        print_accuracy_comparison(X[0], X[1], X[2], tag)
        print(f'\n  Receiver clock bias: {dtr*1e9:.4f} ns  ({dtr:.9f} s)')
        return X, dtr, iters, res, sg

    # ── CASE 1 — three scenarios ──
    print_section('═══  CASE 1: No Corrections  ═══', char=' ', width=60)

    X1a, dtr1a, it1a, res1a, sg1a = _run_and_print(
        f'Case 1A – All sats, no mask ({len(sats_data)} sats)',
        sats_data, case2=False, mask=0.0)

    X1b, dtr1b, it1b, res1b, sg1b = _run_and_print(
        f'Case 1B – Elevation mask {ELEV_MASK:.0f}°',
        sats_data, case2=False, mask=ELEV_MASK)

    X1c, dtr1c, it1c, res1c, sg1c = _run_and_print(
        f'Case 1C – Outlier-rejected ({len(clean_sats)} sats, threshold {OUTLIER_THRS:.0f} m)',
        clean_sats, case2=False, mask=0.0)

    # Use Case 1C as the canonical Case 1 result
    X1, dtr1, iters1, res1, sg1 = X1b, dtr1b, it1b, res1b, sg1b

    # ── CASE 2 — three scenarios ──
    print_section('═══  CASE 2: With Iono + Trop + TGD  ═══', char=' ', width=60)

    X2a, dtr2a, it2a, res2a, sg2a = _run_and_print(
        f'Case 2A – All sats, no mask ({len(sats_data)} sats)',
        sats_data, case2=True, mask=0.0)

    X2b, dtr2b, it2b, res2b, sg2b = _run_and_print(
        f'Case 2B – Elevation mask {ELEV_MASK:.0f}°',
        sats_data, case2=True, mask=ELEV_MASK)

    X2c, dtr2c, it2c, res2c, sg2c = _run_and_print(
        f'Case 2C – Outlier-rejected ({len(clean_sats)} sats, threshold {OUTLIER_THRS:.0f} m)',
        clean_sats, case2=True, mask=0.0)

    # Use Case 2C as the canonical Case 2 result
    X2, dtr2, iters2, res2, sg2 = X2b, dtr2b, it2b, res2b, sg2b


    # ------------------------------------------------------------------
    # J. Earth rotation correction comparison (Case 1C — clean sats only)
    # ------------------------------------------------------------------
    print_section('EARTH ROTATION CORRECTION ANALYSIS')
    sats_no_rot = []
    for sd in clean_sats:
        sp3_win  = sd['sp3_win']
        clk_win  = sp3_win[:, [0, 4]]
        t_nd_n   = clk_win[:, 0]
        c_nd_n   = clk_win[:, 1].copy()
        valid_n  = ~np.isnan(c_nd_n)
        if not valid_n.all() and valid_n.sum() >= 2:
            c_nd_n = np.interp(t_nd_n, t_nd_n[valid_n], c_nd_n[valid_n])
        dt_Pc    = sd['C1'] / c_light
        tems_n   = t_ep - dt_Pc
        for _ in range(2):
            dt_sat_i = lagrange_interp(t_nd_n, c_nd_n, tems_n)
            tems_n   = t_ep - dt_Pc - dt_sat_i
        r_sat_no_rot = interp_sp3_xyz(sp3_win, tems_n)   # no R3 rotation
        sats_no_rot.append({
            'prn'    : sd['prn'],
            'C1'     : sd['C1'],
            'sat_xyz': r_sat_no_rot,
            'dt_sat' : dt_sat_i,
            'TGD'    : sd['TGD'],
            'n_nan_clk': sd.get('n_nan_clk', 0),
        })

    X1_no_rot, _, _, _, _ = spp_least_squares(
        sats_no_rot, apply_corrections=False,
        r_apr_for_atmos=r_apr, elev_mask_deg=0.0, verbose=False)
    diff_rot = X1 - X1_no_rot
    print(f'\n  Receiver position difference due to Earth rotation correction:')
    print(f'    ΔX = {diff_rot[0]:.4f} m')
    print(f'    ΔY = {diff_rot[1]:.4f} m')
    print(f'    ΔZ = {diff_rot[2]:.4f} m')
    print(f'    |Δr| = {np.linalg.norm(diff_rot):.4f} m')

    # ------------------------------------------------------------------
    # K. FINAL SUMMARY
    # ------------------------------------------------------------------
    print_section('FINAL RESULTS SUMMARY — ALL SCENARIOS')
    print(f'\n  Ground Truth (IGS SINEX):')
    print(f'    X = {GT_X:.3f} m  Y = {GT_Y:.3f} m  Z = {GT_Z:.3f} m')
    print()
    header = f'  {"Scenario":<48}  {"3D error [m]":>14}  {"RMS res [m]":>12}'
    print(header)
    print('  ' + '-' * (len(header) - 2))
    for lbl, Xest, rr in [
            ('Case 1A – All sats, no mask',           X1a, res1a),
            ('Case 1B – Elevation mask 10°',           X1b, res1b),
            ('Case 1B – Elev. mask 10° (CANONICAL)',   X1b, res1b),
            ('Case 2A – All sats, no mask',           X2a, res2a),
            ('Case 2B – Elevation mask 10°',           X2b, res2b),
            ('Case 2B – Elev. mask 10° (CANONICAL)',   X2b, res2b)]:
        dX_ = Xest[0] - GT_X
        dY_ = Xest[1] - GT_Y
        dZ_ = Xest[2] - GT_Z
        e3  = math.sqrt(dX_**2 + dY_**2 + dZ_**2)
        rms_r = float(np.sqrt(np.mean(rr**2)))
        print(f'  {lbl:<48}  {e3:>14.3f}  {rms_r:>12.4f}')

    print()
    print(f'  Rejected satellites : {[o[0] for o in outlier_list]}')
    print(f'  Rejection threshold : ±{OUTLIER_THRS:.0f} m deviation from median Lc−rho(GT)')
    print(f'  Median Lc−rho(GT)   : {median_val:.3f} m  (≈ c·dtr receiver clock)')

    # Detail for canonical results
    print()
    for label, Xest in [
            ('Case 1B – Elevation mask 10°, no corrections', X1),
            ('Case 2B – Elevation mask 10°, with corrections  ← FINAL', X2)]:
        dX_ = Xest[0] - GT_X
        dY_ = Xest[1] - GT_Y
        dZ_ = Xest[2] - GT_Z
        e3  = math.sqrt(dX_**2 + dY_**2 + dZ_**2)
        print(f'  {label}:')
        print(f'    X = {Xest[0]:>18.3f} m   (dX = {dX_:+.3f} m)')
        print(f'    Y = {Xest[1]:>18.3f} m   (dY = {dY_:+.3f} m)')
        print(f'    Z = {Xest[2]:>18.3f} m   (dZ = {dZ_:+.3f} m)')
        print(f'    3D positioning error = {e3:.4f} m')

    # Correction contribution (Case 2C minus Case 1C)
    diff12 = X2 - X1
    print(f'\n  Correction effect (Case 2C − Case 1C):')
    print(f'    ΔX = {diff12[0]:.4f} m  '
          f'ΔY = {diff12[1]:.4f} m  '
          f'ΔZ = {diff12[2]:.4f} m  '
          f'|Δr| = {np.linalg.norm(diff12):.4f} m')

    # ------------------------------------------------------------------
    # L. FIGURES
    # ------------------------------------------------------------------
    print('\nGenerating figures ...')

    # Update skyplot geometry with final receiver position (Case 1C)
    for sg in sg1:
        for sd in clean_sats:
            if sd['prn'] == sg['prn']:
                az_s, elev_s, _, _ = local(X1, np.asarray(sd['sat_xyz']))
                sg['az']   = az_s
                sg['elev'] = elev_s
                break

    plot_skyplot(sg1,
                 title=f'Sky Plot – GPS Satellites with 10° Mask (Case 1B, {ELEV_MASK:.0f}° cutoff)',
                 out_path=_out('skyplot_project.png'))
    plot_convergence(iters1, iters2, out_path=_out('convergence_project.png'))
    plot_correction_contributions(sg2, out_path=_out('corrections_project.png'))
    plot_residuals(res1, res2, sg1, sg2, out_path=_out('residuals_project.png'))
    plot_earth_rotation_comparison(X1_no_rot, X1, out_path=_out('earth_rotation_project.png'))

    # Scenario comparison bar chart
    _labels  = ['1A', '1B', '1C', '2A', '2B', '2C']
    _results = [X1a, X1b, X1c, X2a, X2b, X2c]
    _errors  = [math.sqrt((X[0]-GT_X)**2 + (X[1]-GT_Y)**2 + (X[2]-GT_Z)**2)
                for X in _results]
    _colors  = ['#90CAF9','#42A5F5','#1565C0','#EF9A9A','#EF5350','#B71C1C']
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(_labels, _errors, color=_colors, edgecolor='black', linewidth=0.8)
    for bar, val in zip(bars, _errors):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(_errors)*0.01,
                f'{val:.2f} m', ha='center', fontsize=9, fontweight='bold')
    ax.set_ylabel('3D Positioning Error [m]')
    ax.set_xlabel('Scenario')
    ax.set_title('GPS SPP 3D Positioning Error – All Scenarios\n'
                 '(1=Case1 no corr, 2=Case2 with corr; A=all, B=elev mask, C=outlier-rejected)')
    plt.tight_layout()
    plt.savefig(_out('scenario_comparison.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  Saved: {_out("scenario_comparison.png")}')

    print()
    print('=' * 72)
    print('  All done.  Output figures saved to working directory.')
    print('=' * 72)


if __name__ == '__main__':
    main()
