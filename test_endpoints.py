import json

def test_all_api_endpoints():
    from app.main import (
        test_metrics, suite, pipelines, systemic,
        environments, export_metrics, real_pilot, dashboard
    )
    endpoints = {
        'tests': test_metrics,
        'suite': suite,
        'pipelines': pipelines,
        'systemic': systemic,
        'environments': environments,
        'export': export_metrics,
        'real_pilot': real_pilot
    }
    for name, func in endpoints.items():
        data = func()
        assert data is not None
        serialized = json.dumps(data)
        assert len(serialized) > 0

    # Test dashboard endpoint
    dash_resp = dashboard()
    assert dash_resp.status_code == 200
    html_str = dash_resp.body.decode("utf-8")
    assert "FIM // Software Quality Analytics Platform" in html_str
    assert "tab-fim_engine" in html_str
    assert "view-fim_engine" in html_str
    assert "Verified Flaky Candidates" in html_str
    assert "Intermittent Candidates" in html_str
    assert "/api/engine/upload" in html_str
    assert "/api/engine/analyze" in html_str
    assert "/api/engine/download" in html_str
    assert "btn-engine-download-pdf" in html_str
    assert "Research Report PDF" in html_str

if __name__ == '__main__':
    import urllib.request
    endpoints = ['pipelines', 'systemic', 'tests', 'suite', 'environments', 'export']
    try:
        for e in endpoints:
            print(f'\n--- {e} ---')
            response = urllib.request.urlopen(f'http://localhost:8000/api/metrics/{e}')
            data = json.loads(response.read())
            print(json.dumps(data, indent=2))
    except Exception as exc:
        print(f"Direct API inspection (no server at localhost:8000):")
        from app.main import (
            test_metrics, suite, pipelines, systemic,
            environments, export_metrics
        )
        direct = {
            'pipelines': pipelines,
            'systemic': systemic,
            'tests': test_metrics,
            'suite': suite,
            'environments': environments,
            'export': export_metrics
        }
        for e, func in direct.items():
            print(f'\n--- {e} ---')
            data = func()
            print(json.dumps(data, indent=2))
