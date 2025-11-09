# Integration Testing Guide

## Overview

The Markdown Web Browser project includes comprehensive end-to-end integration tests that validate the entire pipeline from browser capture through OCR to markdown generation. These tests use **real services** (no mocks) with extremely detailed logging using the Rich library.

## Test Scripts

### 1. `test_integration_full.py` - Basic Integration Tests
**Purpose**: Quick smoke tests for basic functionality
**Runtime**: ~2-5 minutes

```bash
# Run basic tests
uv run python scripts/test_integration_full.py

# Test against production
uv run python scripts/test_integration_full.py --api-url https://prod.example.com
```

**Features**:
- Health check validation
- Job submission and monitoring
- Artifact retrieval
- Performance metrics
- Rich console output with progress bars

### 2. `test_integration_advanced.py` - Advanced Pipeline Testing
**Purpose**: Detailed pipeline monitoring with live visualization
**Runtime**: ~5-10 minutes

```bash
# Run with live monitoring
uv run python scripts/test_integration_advanced.py

# Custom API endpoint
uv run python scripts/test_integration_advanced.py --api-url http://localhost:8000
```

**Features**:
- Real-time pipeline event tracking
- Live monitoring dashboard
- Multiple test cases (simple, complex, SPA)
- Timeline visualization
- Detailed validation

### 3. `test_e2e_comprehensive.py` - Comprehensive Test Suite
**Purpose**: Production-grade testing with exhaustive validation
**Runtime**: ~15-30 minutes

```bash
# Run all tests (interactive mode)
uv run python scripts/test_e2e_comprehensive.py --interactive

# Run specific category
uv run python scripts/test_e2e_comprehensive.py --category "Smoke Tests"

# Run high-priority tests only
uv run python scripts/test_e2e_comprehensive.py --priority 2

# Run in parallel (experimental)
uv run python scripts/test_e2e_comprehensive.py --parallel 4

# Verbose mode with extra detail
uv run python scripts/test_e2e_comprehensive.py --verbose
```

**Features**:
- Pre-flight system checks
- Comprehensive validation engine
- System resource monitoring
- Test categorization (Smoke, Functional, Performance, Security, Edge Cases, Regression)
- Priority-based execution
- Detailed HTML and JSON reports
- CI/CD integration support

## Test Categories

### Smoke Tests (Priority: CRITICAL)
- API health check
- Simple page capture
- Basic validation

### Functional Tests (Priority: HIGH)
- Complex Wikipedia pages
- GitHub repositories (SPA)
- News articles with media
- Full pipeline validation

### Edge Cases (Priority: MEDIUM)
- Empty pages
- Very long pages
- JavaScript-heavy SPAs
- Unusual content

### Performance Tests (Priority: MEDIUM)
- Response time measurements
- Cache performance
- Large image processing
- Throughput testing

### Security Tests (Priority: HIGH)
- HTTPS enforcement
- Sensitive data detection
- SSL/TLS validation
- Security headers

### Regression Tests (Priority: HIGH)
- Previously failed URLs
- Historical issues
- Backward compatibility

## Validation Levels

### 1. BASIC
- HTTP status codes
- Response times
- Essential checks only

### 2. STANDARD
- Basic + content validation
- Markdown structure
- Link extraction
- Tile generation

### 3. THOROUGH
- Standard + quality checks
- OCR accuracy
- Warning analysis
- Artifact validation

### 4. EXHAUSTIVE
- All possible validations
- Performance profiling
- Security scanning
- Complete analysis

## Output and Reports

### Console Output
All test scripts use Rich library for beautiful console output:
- Color-coded results
- Progress bars with ETA
- Live status updates
- Syntax highlighting
- Tables and trees
- Interactive panels

### HTML Reports
Generated as `test_report_YYYYMMDD_HHMMSS.html`:
- Full test execution log
- Color formatting preserved
- Shareable results
- Browser-viewable

### JSON Reports
Generated as `test_report_YYYYMMDD_HHMMSS.json`:
- Machine-readable format
- CI/CD integration
- Metrics and statistics
- Detailed validation results

## Pre-Flight Checks

The comprehensive test suite performs extensive pre-flight checks:

1. **API Connectivity**: Verifies server is running
2. **Endpoint Availability**: Checks required endpoints
3. **System Resources**: Validates memory and disk space
4. **Dependencies**: Ensures required services are available
5. **Configuration**: Validates settings and credentials

## System Monitoring

During test execution, the system monitors:

- **CPU Usage**: Average and peak utilization
- **Memory Usage**: RAM consumption tracking
- **Network Traffic**: Bytes sent/received
- **API Latencies**: Response time distribution
- **Pipeline Timings**: Stage-by-stage measurements

## Validation Engine

The validation engine performs multiple checks:

### HTTP Validation
- Status codes
- Response times
- Content types
- Headers

### Content Validation
- Markdown structure
- Expected patterns
- Forbidden content
- Link extraction

### Quality Validation
- Tile generation
- OCR accuracy
- Overlap ratios
- Warning analysis

### Performance Validation
- Timing thresholds
- Throughput metrics
- Resource usage
- Cache efficiency

### Security Validation
- HTTPS usage
- Sensitive data exposure
- Security headers
- SSL/TLS configuration

## Running Tests in CI/CD

### GitHub Actions Example
```yaml
- name: Run Integration Tests
  run: |
    # Start server in background
    uv run python scripts/run_server.py &
    sleep 5

    # Run comprehensive tests
    uv run python scripts/test_e2e_comprehensive.py \
      --api-url http://localhost:8000 \
      --priority 2

    # Check results
    if [ -f test_report_*.json ]; then
      python -c "
      import json
      with open('test_report_*.json') as f:
        report = json.load(f)
        success_rate = (report['summary']['passed'] / report['summary']['total']) * 100
        exit(0 if success_rate >= 80 else 1)
      "
    fi
```

### Docker Compose Testing
```bash
# Start services
docker-compose up -d

# Wait for services
sleep 10

# Run tests against containers
uv run python scripts/test_e2e_comprehensive.py \
  --api-url http://localhost:8000

# Cleanup
docker-compose down
```

## Troubleshooting

### Common Issues

1. **Connection Refused**
   - Ensure server is running: `uv run python scripts/run_server.py`
   - Check port availability: `lsof -i :8000`

2. **OCR Timeouts**
   - Verify OCR credentials in `.env`
   - Check network connectivity
   - Consider using mock OCR server for testing

3. **Resource Exhaustion**
   - Monitor system resources during tests
   - Reduce parallel test execution
   - Increase timeout values

4. **Flaky Tests**
   - Add retries for network operations
   - Increase settling times for dynamic content
   - Use more lenient validation thresholds

## Best Practices

1. **Start with Smoke Tests**: Run quick smoke tests before comprehensive suite
2. **Use Interactive Mode**: For first-time setup and debugging
3. **Monitor Resources**: Keep an eye on CPU/memory during tests
4. **Review Reports**: Always check HTML reports for detailed results
5. **Version Control**: Commit test reports for historical tracking
6. **Regular Execution**: Run tests regularly to catch regressions early
7. **Custom Test Cases**: Add project-specific test cases as needed

## Extending the Tests

### Adding Custom Test Cases

```python
# In test_e2e_comprehensive.py
custom_test = TestCase(
    id="custom_001",
    name="My Custom Test",
    description="Test specific functionality",
    category=TestCategory.FUNCTIONAL,
    priority=TestPriority.HIGH,
    url="https://mysite.com",
    timeout=60.0,
    expected_tiles_min=2,
    expected_markdown_patterns=[r"Expected Content"],
    validation_level=ValidationLevel.THOROUGH,
    tags={"custom", "specific"}
)
```

### Adding Custom Validators

```python
# In ValidationEngine class
async def _validate_custom(self, test_case: TestCase, data: Dict[str, Any]) -> ValidationResult:
    """Custom validation logic."""
    # Your validation logic here
    return ValidationResult(
        passed=True,
        category="custom",
        check_name="my_check",
        expected="expected_value",
        actual="actual_value",
        message="Validation message",
        severity="info"
    )
```

## Performance Tips

1. **Caching**: Enable `use_cache=True` for repeated tests
2. **Parallel Execution**: Use `--parallel` flag (experimental)
3. **Selective Testing**: Use category/priority filters
4. **Resource Limits**: Set appropriate timeouts
5. **Mock Services**: Use mock OCR for development testing

## Conclusion

The integration test suite provides comprehensive validation of the Markdown Web Browser pipeline. With detailed logging, thorough validation, and beautiful Rich formatting, these tests ensure the system works correctly end-to-end with real services and real data.