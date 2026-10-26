"""Import data only; never execute an AI Studio C export. No model is supplied."""
import argparse
import hashlib
import json
from pathlib import Path
import re

EXPECTED_BYTES = 2001

def parse_export(path):
    if path.suffix.lower() == '.bin':
        data = path.read_bytes()
    else:
        text = re.sub(r'/\*.*?\*/|//[^\n]*', '', path.read_text(encoding='utf-8-sig'), flags=re.S)
        matches = re.findall(r'\b(?:const\s+)?uint8_t\s+bsec_config_selectivity\s*\[\s*\d*\s*\]\s*=\s*\{([^}]+)\}\s*;', text, re.S)
        if len(matches) != 1:
            raise ValueError('Expected exactly one uint8_t bsec_config_selectivity array')
        tokens = [v.strip() for v in matches[0].split(',') if v.strip()]
        if any(not re.fullmatch(r'(?:0[xX][0-9a-fA-F]+|[0-9]+)', t) for t in tokens):
            raise ValueError('Only literal byte values allowed; C expressions are rejected')
        data = bytes(int(t, 16 if t.lower().startswith('0x') else 10) for t in tokens)
    if len(data) != EXPECTED_BYTES:
        raise ValueError(f'Expected {EXPECTED_BYTES} bytes for pinned BSEC 3.3; got {len(data)}')
    return data

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('--name', required=True)
    parser.add_argument('--mold-class', type=int, required=True, help='ZERO-based class channel; verify exported label map')
    parser.add_argument('--class-count', type=int, required=True, choices=range(2, 5))
    parser.add_argument('--bsec-version', required=True, choices=['3.3.0.0'])
    parser.add_argument('--validated', action='store_true', help='Explicit operator assertion, not automatic certification')
    parser.add_argument('--validation-report', type=Path)
    parser.add_argument('--validation-quality', type=float, default=0)
    parser.add_argument('--stale-ms', type=int, default=45000, help='Must exceed complete scan interval with margin')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1]/'src/Models/MoldModelData.h')
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    if not 0 <= args.mold_class < args.class_count:
        parser.error('mold-class must be less than class-count')
    if not 3000 <= args.stale_ms <= 300000:
        parser.error('stale-ms must be between 3000 and 300000')
    if not 0 <= args.validation_quality <= 1:
        parser.error('validation-quality must be finite in [0,1]')
    if args.validated and (not args.validation_report or not args.validation_report.is_file() or not args.validation_quality > 0):
        parser.error('--validated requires a saved validation report and quality > 0')
    if len(args.name) > 48 or not re.fullmatch(r'[A-Za-z0-9 _.-]+', args.name):
        parser.error('name must be 1-48 plain ASCII letters/numbers/space/underscore/dot/hyphen')
    if args.output.exists() and not args.replace:
        parser.error('output already exists; use --replace to replace it deliberately')
    try:
        data = parse_export(args.export)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    report_hash = hashlib.sha256(args.validation_report.read_bytes()).hexdigest() if args.validation_report else 'NONE'
    sha = hashlib.sha256(data).hexdigest()
    lines = ['#pragma once', '#include <stdint.h>', '#include <stddef.h>', 'namespace moldmodel {',
        'constexpr bool installed=true;', f'constexpr bool validated={str(args.validated).lower()};',
        f'constexpr uint8_t moldClass={args.mold_class},classCount={args.class_count};',
        f'constexpr float validationQuality={args.validation_quality:.6f}f;',
        f'constexpr uint32_t staleMs={args.stale_ms};', f'constexpr const char* name={json.dumps(args.name)};',
        f'constexpr const char* sha256="{sha}";', f'constexpr const char* validationReference="{report_hash}";',
        'constexpr uint8_t data[]={']
    lines += [','.join(map(str, data[i:i+24]))+',' for i in range(0, len(data), 24)]
    lines += ['};', 'constexpr size_t size=sizeof(data);', '}']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.tmp')
    temporary.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    temporary.replace(args.output)
    print(json.dumps({'file':str(args.output),'bytes':len(data),'sha256':sha,'validated_assertion':args.validated,'report_sha256':report_hash}, indent=2))

if __name__ == '__main__':
    main()
