import requests

# Login as admin
r = requests.post('http://localhost:8000/api/token', data={'username':'Juan Ramon','password':'123456'})
if r.status_code != 200:
    print("Login failed")
    exit(1)

token = r.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

# Check system stats
r = requests.get('http://localhost:8000/api/stats', headers=headers)
if r.status_code == 200:
    stats = r.json()
    print('=== ESTADÍSTICAS DEL SISTEMA ===')
    print(f'CPU Usage: {stats.get("cpu_percent", "N/A")}%')
    print(f'Memory Usage: {stats.get("memory_percent", "N/A")}%')
    print(f'Disk Usage: {stats.get("disk_percent", "N/A")}%')

    if 'system' in stats:
        system = stats['system']
        print(f'Active Tasks: {system.get("active_tasks", "N/A")}')
        print(f'Failed Tasks: {system.get("failed_tasks", "N/A")}')
        print(f'Failures Count: {system.get("failures_count", "N/A")}')

    if 'llm' in stats:
        llm = stats['llm']
        print(f'LLM Requests: {llm.get("requests", "N/A")}')
        print(f'LLM Errors: {llm.get("errors", "N/A")}')
        print(f'LLM Busy Rate: {llm.get("busy_rate", "N/A")}')
else:
    print(f"Error getting stats: {r.status_code}")
    print(r.text)