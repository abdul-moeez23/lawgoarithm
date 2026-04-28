# Lawyer Platform - Docker Setup

This project is containerized using Docker and Docker Compose. It includes the Django web application, a PostgreSQL database, and pgAdmin for database management.

## Prerequisites

- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Quick Start

To run the project, follow these steps:

1.  **Clone the repository** (if you haven't already):
    ```bash
    git clone <repository-url>
    cd lawyer_platformm
    ```

2.  **Run the project with Docker Compose**:
    ```bash
    docker-compose up --build
    ```

3.  **Access the applications**:
    - **Web Application**: [http://localhost:8001](http://localhost:8001)
    - **pgAdmin**: [http://localhost:5051](http://localhost:5051)
        - **Login Email**: your pgAdmin email
        - **Login Password**: your pgAdmin password

## Database Management with pgAdmin

1.  Log in to pgAdmin at [http://localhost:5051](http://localhost:5051).
2.  Add a new server:
    - **Name**: Lawyer DB (or any name you prefer)
    - **Connection Tab**:
        - **Host name/address**: `db`
        - **Port**: `5432`
        - **Maintenance database**: your database name
        - **Username**: your database user
        - **Password**: your database password
3.  Click **Save**.

> [!NOTE]
> If you want to connect to the database from an external tool (like DBeaver or pgAdmin installed on your host), use `localhost` as the host and `5435` as the port.

## Useful Commands

- **Stop the containers**:
    ```bash
    docker-compose down
    ```
- **Stop and remove volumes (reset database)**:
    ```bash
    docker-compose down -v
    ```
- **Create a superuser**:
    ```bash
    docker-compose exec web python manage.py createsuperuser
    ```
- **Run migrations**:
    ```bash
    docker-compose exec web python manage.py migrate
    ```

## Environment Variables

The project uses a dedicated settings file for Docker located at `lawyer_platform/settings/docker.py`. It reads database credentials from environment variables defined in `docker-compose.yml`.
