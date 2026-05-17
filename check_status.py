import requests

# Login as admin
r = requests.post('http://localhost:8000/api/token', data={'username':'Juan Ramon','password':'123456'})
if r.status_code != 200:
    print("Login failed")
    exit(1)

token = r.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

# Check system status
r = requests.get('http://localhost:8000/api/status', headers=headers)
if r.status_code == 200:
    status = r.json()
    print('=== ESTADO DEL SISTEMA ===')
    print(f'Status: {status.get("status", "unknown")}')
    print(f'Workers: {status.get("workers_alive", 0)}/3')
    print(f'Queue Depth: {status.get("queue_depth", 0)}')

    features = status.get('features', {})
    print(f'Evolución automática: {features.get("evolution", False)}')
    print(f'Destilación: {features.get("distillation", False)}')
    print(f'Proactivo: {features.get("proactive", False)}')
    print(f'Investigación autónoma: {features.get("autonomous_research", False)}')
else:
    print(f"Error: {r.status_code}")
    print(r.text)