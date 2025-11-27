# Test Scripts

Test utilities for CQSentinel development and debugging.

## Hamlib RF Controls Tests

### test_hamlib_levels.py
Tests hamlib RF control level commands.

**Requirements**: rigctld must be running separately

```bash
python test_hamlib_levels.py
```

### test_hamlib_levels_standalone.py
Standalone hamlib tester that bundles and starts rigctld automatically.

**No external dependencies** - includes rigctld

```bash
python test_hamlib_levels_standalone.py
```

**Build as executable**:
```bash
..\build_hamlib_test.bat
```

Output: `dist/HamlibRFTest.exe`

### test_rf_controls.py
Interactive test for RF gain, preamp, and attenuator controls.

**Requirements**: rigctld running

```bash
python test_rf_controls.py
```

## Usage

These scripts help verify hamlib control functionality with your radio before using the main CQSentinel application. Useful for:

- **Debugging** RF control issues
- **Verifying** radio compatibility
- **Testing** new hamlib features
- **Isolating** problems from the main application

## Common Radio Models

| Radio | Hamlib ID | Notes |
|-------|-----------|-------|
| Icom IC-705 | 3085 | Preamp uses indices (0, 1, 2) |
| Yaesu FT-710 | 1049 | Preamp uses dB values |
| Icom IC-7300 | 3073 | Similar to IC-705 |

## See Also

- **Main docs**: [../../HAMLIB_TEST_README.txt](../../HAMLIB_TEST_README.txt)
- **Build scripts**: [../build_hamlib_test.bat](../build_hamlib_test.bat)
- **PyInstaller spec**: [../HamlibRFTest.spec](../HamlibRFTest.spec)
