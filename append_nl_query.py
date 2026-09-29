content = """
class NLQueryRequest(BaseModel):
    query: str


@app.post("/query")
def nl_query(request: NLQueryRequest) -> dict[str, Any]:
    \"\"\"Process a natural language query about dashboard data.\"\"\"
    result = process_nl_query(request.query)
    return {
        \"query\": request.query,
        \"answer\": result.answer,
        \"data\": result.data,
        \"query_type\": result.query_type,
    }
"""
with open('C:/Users/Aryamann Sharma/Documents/Claude Code Workspace/heatwave-ews/backend/app/main.py', 'a') as f:
    f.write(content)
print('Done')