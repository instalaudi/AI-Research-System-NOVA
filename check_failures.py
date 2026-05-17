import requests

# Try login with Juan Ramon - common passwords
passwords = ['admin', '123456', 'password', 'juanramon', 'juan', 'ramon']

for pwd in passwords:
    r = requests.post('http://localhost:8000/api/token', data={'username':'Juan Ramon','password':pwd})
    if r.status_code == 200:
        data = r.json()
        print(f'Login successful with password: {pwd}')
        print(f'Is admin: {data.get("is_admin", False)}')
        if data.get('is_admin', False):
            token = data['access_token']
            headers = {'Authorization': f'Bearer {token}'}
            r2 = requests.get('http://localhost:8000/api/system/failures', headers=headers)
            if r2.status_code == 200:
                failures = r2.json()
                print(f'Encontrados {len(failures)} errores registrados')
                for i, f in enumerate(failures[:3]):
                    print(f'{i+1}. Tipo: {f.get("error_type", "Unknown")}')
                    print(f'   Mensaje: {f.get("message", "No message")[:150]}...')
                    print(f'   Timestamp: {f.get("timestamp", "Unknown")}')
                    print()
            break
        else:
            print('Usuario no es admin')
            break
    else:
        print(f'Failed with password: {pwd}')