# S3 Drive

S3 Drive is a Google Drive–like file management system built on top of Amazon S3. It is designed for one-to-one organizational use, providing secure file storage along with **RBAC-based user access control**.

You can set up S3 Drive in either of the following ways:

* **Use your own S3 credentials** and configure your S3 storage.
* **Use the default S3 configuration** provided by S3 Drive.

It provides a simple, familiar file-management experience while leveraging S3 for scalable and reliable storage.

## Development with Docker Compose

Run the stack with live reload for both the API and UI:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

API changes reload through Uvicorn, and UI changes reload through Next.js. Open the UI at `http://localhost:3000`.
