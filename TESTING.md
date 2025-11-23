# 🧪 Quick Test Guide

## Run Tests (3 Easy Steps)

### Windows
```powershell
.\run-tests.ps1
```

### Linux/Mac
```bash
chmod +x run-tests.sh
./run-tests.sh
```

---

## What Gets Tested? ✅

**60+ comprehensive tests covering:**

### Core Functionality
- ✅ Configuration loading & validation
- ✅ Wowza event translation (10+ event types)
- ✅ Slack message formatting & sending
- ✅ Error handling & edge cases

### Advanced Features
- ✅ Video Intelligence detection batching
- ✅ AI object tracking across frames
- ✅ IoU (Intersection over Union) calculations
- ✅ Thread safety & race conditions

### API Endpoints
- ✅ `/health` - Health check endpoint
- ✅ `/webhook` - Wowza webhook receiver
- ✅ Invalid JSON handling
- ✅ Malformed payload protection

### Reliability
- ✅ Graceful shutdown handling
- ✅ Memory limits (batch size protection)
- ✅ Timeout handling
- ✅ Configuration fallbacks

---

## Test Results Format

```
======================== test session starts ========================
test_http_server.py::TestConfiguration::test_load_config ✓ PASSED
test_http_server.py::TestIoUCalculation::test_perfect_overlap ✓ PASSED
test_http_server.py::TestEventTranslation::test_stream_started ✓ PASSED
...
======================== 60 passed in 2.45s =========================
```

---

## Common Commands

### Run specific test category
```bash
pytest test_http_server.py::TestConfiguration -v
pytest test_http_server.py::TestVIBatching -v
pytest test_http_server.py::TestFlaskEndpoints -v
```

### Run tests matching keyword
```bash
pytest test_http_server.py -k "iou" -v        # All IoU tests
pytest test_http_server.py -k "slack" -v      # All Slack tests
pytest test_http_server.py -k "webhook" -v    # All webhook tests
```

### Generate coverage report
```bash
pytest test_http_server.py --cov=http_server --cov-report=html
# Open htmlcov/index.html in browser
```

---

## Test Categories

| Category | Tests | What It Covers |
|----------|-------|----------------|
| **Configuration** | 4 | Environment variables, validation, fallbacks |
| **Utilities** | 6 | URL sanitization, timestamp formatting |
| **IoU Calculation** | 6 | Bounding box overlap for tracking |
| **Object Tracking** | 5 | AI multi-frame person tracking |
| **Event Translation** | 7 | Wowza → Human-readable messages |
| **VI Batching** | 5 | Detection batching, memory limits |
| **Flask Endpoints** | 5 | `/health`, `/webhook` API tests |
| **Slack Integration** | 3 | Message sending, fallback logic |
| **Graceful Shutdown** | 1 | Clean termination, batch flushing |
| **Thread Safety** | 1 | Concurrent webhook handling |

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'pytest'"
**Solution:** Install test dependencies
```bash
pip install -r requirements-test.txt
```

### "ImportError: cannot import name 'http_server'"
**Solution:** Ensure you're in the correct directory
```bash
cd "c:\Users\alex.chepurnoy\Documents\Self Made Tools\WS_Slack_Translator"
python test_http_server.py
```

### Tests hang or timeout
**Solution:** Press Ctrl+C and check for uncancelled timers
```bash
# Run with timeout
pytest test_http_server.py --timeout=30
```

### Permission denied (run-tests.sh)
**Solution:** Make script executable
```bash
chmod +x run-tests.sh
./run-tests.sh
```

---

## Manual Test Execution

Without the helper scripts:

```bash
# 1. Create virtual environment (optional)
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\Activate.ps1  # Windows

# 2. Install dependencies
pip install -r requirements-test.txt

# 3. Run tests
python -m pytest test_http_server.py -v
```

---

## What's NOT Tested?

These require manual/integration testing:
- ❌ Live Slack API calls (mocked in tests)
- ❌ Actual Wowza webhook integration
- ❌ Docker container behavior
- ❌ Network timeouts under load
- ❌ Production Gunicorn worker behavior

**Use `test-docker.ps1` for containerized integration testing**

---

## CI/CD Integration

Add to your pipeline:

```yaml
# GitHub Actions example
steps:
  - name: Install dependencies
    run: pip install -r requirements-test.txt
  
  - name: Run tests
    run: pytest test_http_server.py -v --cov=http_server
  
  - name: Upload coverage
    uses: codecov/codecov-action@v3
```

---

## Next Steps

1. **Run the tests**: `.\run-tests.ps1`
2. **Check coverage**: `pytest test_http_server.py --cov=http_server --cov-report=html`
3. **Read detailed docs**: See `TEST_GUIDE.md`
4. **Integration test**: Use `test-docker.ps1` for full stack testing

---

## Support

- 📖 Full documentation: `TEST_GUIDE.md`
- 🐳 Docker testing: `test-docker.ps1` or `test-docker.sh`
- 🔧 Main docs: `README.md` and `DOCKER_README.md`

**All tests should pass with 60/60 ✓**
