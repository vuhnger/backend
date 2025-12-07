# vuhnger/backend

A lightweight backend built with **FastAPI** and **Docker**, designed to run multiple small services (e.g., calendar, blog, Strava tracking).  
The project is fully portable — it can run on NREC, local Docker, or any cloud provider that supports containers.

## 🚀 Features

- FastAPI application  
- Modular structure (`apps/<service>/main.py`)  
- Docker containerization  
- Docker Compose for local or server deployment  
- CORS configured for your domains  
- Easy to extend with new services  

## 📦 Repository Structure

```
backend/
├── apps/
│   └── calendar/
│       └── main.py
├── Caddyfile
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 🛠 Requirements

You need **Docker** and **Docker Compose**.

### On macOS  
Docker Desktop includes everything:  
https://www.docker.com/products/docker-desktop/

### On Linux  
Install Docker + the Compose plugin using your package manager.

## ▶️ Running the Backend (Local or Server)

Clone the repo:

```bash
git clone https://github.com/vuhnger/backend.git
cd backend
```

Build and start the backend:

```bash
docker compose up -d --build
```

Check that it works:

```bash
curl http://localhost:5001/calendar/health
```

Expected output:

```json
{"status": "ok"}
```

## 🧱 Adding New Services

To add another microservice:

1. Create a folder such as:
```
apps/blog/main.py
```
2. Implement FastAPI routes there.  
3. Update `Caddyfile` if you want it exposed publicly.  
4. Rebuild:

```bash
docker compose up -d --build
```

## 🌍 Deployment

### **NREC**

The backend runs behind **Caddy**, which handles HTTPS and routing.

Deploy updates with:

```bash
git pull
docker compose up -d --build
```

### Other platforms

This backend is portable to any Docker-friendly platform (Fly.io, Railway, Vultr, etc).

