content = '''

class DemoRunRequest(BaseModel):
    scenario: str


@app.post("/demo/run")
def run_demo(request: DemoRunRequest) -> dict[str, Any]:
    """Run a scripted demo scenario from stored data (no network)."""
    from pipeline.demo import run_demo_scenario, list_demo_scenarios
    available = list_demo_scenarios()
    if request.scenario not in available:
        raise HTTPException(status_code=404, detail=f"Scenario not found. Available: {available}")
    return run_demo_scenario(request.scenario)


@app.get("/demo/scenarios")
def list_demos() -> dict[str, Any]:
    """List available demo scenarios."""
    from pipeline.demo import list_demo_scenarios
    return {"scenarios": list_demo_scenarios()}
'''
with open('C:/Users/Aryamann Sharma/Documents/Claude Code Workspace/heatwave-ews/backend/app/main.py', 'a') as f:
    f.write(content)
print('Done')