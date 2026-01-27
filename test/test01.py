import requests

url = "http://127.0.0.1:8001/process_pdf"
files = {'file': open('./data/test/test02.pdf', 'rb')}

response = requests.post(url, files=files)
print(response.json())