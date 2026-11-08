# DevOps Dashboard

Homework 2 demo service for “From Development to Deployment”.

## Run

```powershell
npm start
```

Open http://127.0.0.1:3000 and check http://127.0.0.1:3000/health.

The server reads the hosting platform's `PORT` environment variable and listens on all network interfaces for deployment.

## DevOps points

- Source: project files are kept in a version-control-ready structure.
- Build/Test: the service uses Node.js core modules and exposes a health endpoint.
- Deploy/Monitor: the dashboard shows release and service status in the browser.

