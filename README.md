# ChargeGrid

A user-side EV charging app simulation for finding chargers, completing a charging journey and managing a virtual wallet.

> This is a simulation. No real chargers, hardware or money are involved.

[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![React](https://img.shields.io/badge/React-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![Supabase](https://img.shields.io/badge/Supabase-3FCF8E?logo=supabase&logoColor=white)](https://supabase.com/)
[![MQTT](https://img.shields.io/badge/MQTT-660066?logo=eclipse-mosquitto&logoColor=white)](https://mqtt.org/)

## Overview

ChargeGrid is a college-project simulation of the user-facing side of an EV charging system. It lets a signed-in user choose a vehicle, find simulated stations, reserve and use a compatible charger, complete a trip or charging session and review bills and wallet transactions. The backend accelerates and controls the simulated clock, chargers, other drivers, faults and station power sharing.

It is a full software demo rather than a hardware integration: the REST API, authentication tokens, journey logic, billing rules and optional database persistence are real parts of this project. The stations, vehicles, tariffs and payments are illustrative demo data. No real charger can be contacted and no real money moves.


## Table of Contents

- [Features](#features)
- [Simulation scope](#simulation-scope)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Demo walkthrough](#demo-walkthrough)
- [API overview](#api-overview)
- [Testing](#testing)
- [Known limitations](#known-limitations)
- [Roadmap / future work](#roadmap--future-work)
- [Acknowledgements and License](#acknowledgements-and-license)

## Features

### Find and reserve
- Map and list of simulated stations in and around Chennai.
- Distance, estimated arrival charge and compatible charger information.
- Filters for compatible chargers, DC chargers and currently available chargers.
- Reservation holds with a configurable real-time duration.

### Journey and charging
- Name-and-PIN signup and login.
- Vehicle selection and battery-level controls.
- Simulated driving to a station.
- Connector compatibility checks.
- Plug-in handshake, target charge and optional spending cap.
- AC/DC charging with station power sharing and simulated faults.
- Target reached, manual stop, spending-cap stop and unplug flows.

### Billing and wallet
- Peak, standard and off-peak tariff multipliers.
- Itemised energy billing with tax.
- Idle fees after a stopped charging session.
- A virtual welcome balance and wallet top-ups.
- Invoice payment from the simulated wallet, with unpaid-invoice blocking.

### History and analytics
- Charging session history.
- Energy, spend and session summary values.
- Daily energy and spend charts.
- Detailed invoices and itemised bill lines.

### Demo and simulation controls
- Global simulation speeds of 1x, 10x, 20x, 60x and 120x.
- Quiet, normal and busy simulated background traffic.
- A "break my charger" demo control.
- Simulated battery trip usage.
- Optional notices for low battery, reservation expiry, faults and completed sessions.

## Simulation scope

| Simulated | Real in this project |
|---|---|
| Chargers and their availability, faults and power sharing | Flask REST API and JSON responses |
| Other vehicles and background station traffic | Name-and-PIN demo authentication and bearer tokens |
| Station locations, vehicles and charging data | Journey, reservation and charging-state logic |
| Grid conditions, tariffs, peak/off-peak periods and the accelerated clock | Energy-cost, tax, idle-fee and wallet billing logic |
| Wallet top-ups and invoice payments | React and Vite browser application |
| MQTT-style charger messages and optional external MQTT mirror | Optional Supabase/Postgres persistence |

## Architecture

```
  Browser (React + Vite, Tailwind, Leaflet, Recharts)
        |   HTTP + JSON  (Authorization: Bearer <token>)
        v
  Flask API  (backend/app.py)
        |
        v
  cloud.py  services: auth, availability, reservations, journey, billing, wallet
        |  reads state / sends commands only through the bus
        v
      bus.py  (in-process pub/sub with MQTT-style topics, optional MQTT mirror)
        ^
        |  status, telemetry, ticks
  simulator.py  devices: chargers, background traffic, faults, sim clock

  cloud.py --> repo.py --> Supabase (Postgres)      (falls back to memory if Supabase is not configured)
```

`cloud.py` talks to the simulated chargers only through `bus.py`: it subscribes to status and telemetry and publishes charger commands. This mirrors how a real cloud backend could communicate with charging hardware through MQTT. The MQTT mirror is optional.

## Tech stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend API | Python 3, Flask, flask-cors | REST endpoints, CORS and JSON responses |
| Simulation | Python threads, `Simulator`, `Bus` | Charger state, background traffic, faults and accelerated clock |
| Data | Memory backend or Supabase/Postgres | Demo storage with optional persistence |
| Auth | Werkzeug password hashing, `itsdangerous` | PIN hashes and signed bearer tokens |
| Optional messaging | Paho MQTT | Mirrors bus topics to an external MQTT broker |
| Frontend | React 18, React Router | SPA screens and navigation |
| Frontend build | Vite 5 | Development server and production build |
| Styling | Tailwind CSS 3 | Responsive interface styles |
| Maps and charts | Leaflet, React Leaflet, Recharts | Station map and charging history charts |
| Testing | pytest | API and full in-memory journey flow tests |

## Project structure

```text
.
├── backend/
│   ├── app.py                  # Flask app and REST routes
│   ├── cloud.py                # Auth, journeys, reservations and billing
│   ├── simulator.py            # Simulated chargers, drivers, faults and clock
│   ├── bus.py                  # In-process MQTT-style pub/sub and optional mirror
│   ├── repo.py                 # Memory and Supabase repository backends
│   ├── config.py               # Environment configuration
│   ├── seed.py                 # Seed vehicles and illustrative stations
│   ├── supabase_schema.sql     # Optional Supabase/Postgres schema
│   ├── .env.example            # Backend environment template
│   ├── requirements.txt        # Python dependencies
│   └── tests/test_flow.py      # API and journey tests
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Routes and authenticated app shell
│   │   ├── store.jsx           # Shared frontend state and API polling
│   │   ├── api.js              # Single frontend API client
│   │   ├── pages/              # Home, Find, Charge, Wallet, History and Profile screens
│   │   └── components/         # Shared UI components
│   ├── CONTRACT.md             # Frontend/backend API contract
│   ├── .env.example            # Frontend environment template
│   └── package.json            # Frontend dependencies and scripts
└── README.md
```

## Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer
- npm
- Optional: a Supabase project

## Getting started

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd chargegrid-user-app
```

### 2. Set up the backend

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment:

**macOS or Linux**

```bash
source .venv/bin/activate
```

**Windows PowerShell**

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies and create the backend environment file:

```bash
pip install -r requirements.txt
cp .env.example .env
python app.py
```

**Windows Command Prompt**

```bat
copy .env.example .env
python app.py
```

The backend listens on `http://localhost:5000`.

### 3. Set up the frontend

Open another terminal:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

**Windows Command Prompt**

```bat
copy .env.example .env
npm run dev
```

The frontend is served at `http://localhost:5173`.

### 4. Configure Supabase optionally

Without Supabase, the app uses memory storage and forgets data when the backend restarts.

1. Create a Supabase project.
2. Open the SQL Editor, paste the complete contents of `backend/supabase_schema.sql`, and run it.
3. Open the project API settings and copy the project URL and secret key.
4. Set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in `backend/.env`.
5. Restart the backend and check `http://localhost:5000/api/health`. Persistence is active when `persistent` is `true`.

Never use the Supabase secret key in the frontend or commit it to source control.

## Configuration

Every variable in `backend/.env.example` and `frontend/.env.example` is listed below.

| Variable | Default | Meaning |
|---|---|---|
| `SUPABASE_URL` | placeholder | Supabase project URL. Placeholder values fall back to memory storage. |
| `SUPABASE_SERVICE_KEY` | placeholder | Supabase service-role secret key. Used only by the backend. |
| `APP_SECRET_KEY` | `dev-secret-change-me` | Long-term secret used to sign login bearer tokens. |
| `PORT` | `5000` | Flask backend port. |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated browser origins allowed by CORS. |
| `RESERVATION_HOLD_SECONDS` | `300` | Real seconds before an unused reservation expires. |
| `TAX_PERCENT` | `18` | Tax percentage added to invoice totals. |
| `MIN_WALLET_TO_START` | `100` | Minimum wallet balance required before charging can start. |
| `DEFAULT_SIM_SPEED` | `20` | Initial simulation speed: 1, 10, 20, 60 or 120. |
| `MQTT_HOST` | empty | MQTT broker host. Leave empty to disable the mirror. |
| `MQTT_PORT` | `1883` | MQTT broker port. |
| `MQTT_USERNAME` | empty | Optional MQTT username. |
| `MQTT_PASSWORD` | empty | Optional MQTT password. |
| `VITE_API_BASE_URL` | `http://localhost:5000` | Frontend URL used to call the Flask API. |

Never commit `.env` files or the Supabase secret key. Use a strong `APP_SECRET_KEY` and keep any optional MQTT credentials private.

## Demo walkthrough

1. **Create two demo accounts.** Sign up as Asha in one browser window and Bala in another. Use different names and vehicle models.
2. **Open the Find screen.** Watch the station free counts update as the simulated clock and background traffic advance.
3. **Reserve a compatible charger.** Open a station, choose an available charger and reserve it. The charge journey shows a five-minute hold by default.
4. **Start the journey.** Press **Go now** and let the simulated drive finish. When it says that you have arrived, press **Plug in**.
5. **Charge and review the bill.** Wait for the connection handshake, set a target and optional spending cap, then start charging. Stop or unplug, then review and pay the simulated invoice.

The Profile screen's **Simulation** panel exposes speed, traffic, battery and fault controls. With two accounts at the same station, the station power cap can be used to demonstrate power sharing.

## API overview

The table lists the main routes. [frontend/CONTRACT.md](frontend/CONTRACT.md) is the detailed API contract.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Backend, persistence and simulation health |
| `GET` | `/api/vehicles` | Public vehicle catalogue |
| `POST` | `/api/auth/signup` | Create a demo account |
| `POST` | `/api/auth/login` | Sign in and receive a bearer token |
| `GET` | `/api/me` | Current profile, vehicle and battery |
| `PATCH` | `/api/me` | Change vehicle or battery while idle |
| `GET` | `/api/wallet` | Balance and transactions |
| `POST` | `/api/wallet/topup` | Add a simulated wallet top-up |
| `GET` | `/api/stations` | Nearby stations and charger status |
| `GET` | `/api/stations/<sid>` | One station and its chargers |
| `POST` | `/api/reservations` | Reserve a charger |
| `DELETE` | `/api/reservations/<rid>` | Cancel a reservation |
| `GET` | `/api/journey` | Current journey state and notices |
| `POST` | `/api/journey/go` | Start the simulated drive |
| `POST` | `/api/journey/plug-in` | Plug into the arrived charger |
| `POST` | `/api/journey/start` | Start charging |
| `POST` | `/api/journey/stop` | Stop charging |
| `POST` | `/api/journey/unplug` | Unplug and create or show an invoice |
| `POST` | `/api/journey/dismiss` | Leave the invoice state |
| `POST` | `/api/trips` | Simulate round-trip battery usage |
| `GET` | `/api/sessions` | Charging history and analytics |
| `GET` | `/api/invoices/<iid>` | One invoice |
| `POST` | `/api/invoices/<iid>/pay` | Pay an invoice from the wallet |
| `GET` | `/api/sim/settings` | Read simulation speed and traffic |
| `POST` | `/api/sim/settings` | Change simulation speed or traffic |
| `POST` | `/api/sim/break-my-charger` | Fault the user's current charger |

## Testing

From the repository root:

```bash
cd backend
pytest -q
```

The tests use an in-memory repository and run the simulator manually. They cover signup and login, connector compatibility, reservations and expiry, driving and low-battery trips, power sharing, idle fees, invoices and wallet balances, spending caps, faults, restart recovery and zero-distance trips.

## Known limitations

- Authentication is demo-grade: name plus 4-digit PIN, signed bearer tokens and no real identity provider.
- Payments are simulated wallet balances. No real money is accepted or transferred.
- Station locations, vehicle specifications, chargers, tariffs, peak hours and tax values are illustrative.
- The app runs as a single backend process. The simulator, bus and in-memory state do not support multiple workers or replicas.
- Simulation speed and traffic settings are global and shared by every signed-in user.
- The Ready to charge estimate ignores taper and power sharing and can differ from the delivered bill.
- Supabase persistence has not been end-to-end tested against a live Supabase project in this repository.
- The external MQTT mirror has not been tested against a live MQTT broker.
- The Supabase schema is protected with RLS and no frontend policies; the secret-key backend is the intended database client.

## Roadmap / future work

- Add real account and identity-provider authentication.
- Add a deployable and documented MQTT integration.
- Add a persistent multi-process simulation service.
- Add automated frontend tests and a production build check.
- Add more realistic charger and route data.
- Add license selection and deployment documentation.

## Acknowledgements and License

Built as a college-project EV charging simulation.
