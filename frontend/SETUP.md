# Setup Instructions - Frontend

## Prerequisites
- Node.js 18+ and npm

## Installation

### 1. Install dependencies
```bash
npm install
```

### 2. Configure environment
```bash
cp .env .env.local  # Or edit existing .env
```

Current `.env` settings:
```
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### 3. Development server
```bash
npm run dev
```

App will be available at: http://localhost:5173

## Available Commands
```bash
npm run dev      # Start dev server with HMR
npm run build    # Production build
npm run preview  # Preview production build
npm run lint     # Run ESLint
npm run start    # Alias for dev
```

## Project Structure
```
frontend/
├── src/
│   ├── components/      # React components
│   ├── pages/          # Page components
│   ├── hooks/          # Custom React hooks
│   ├── services/       # API services (axios)
│   ├── store/          # Zustand state management
│   ├── styles/         # CSS/Tailwind styles
│   └── App.jsx
├── public/             # Static assets
└── vite.config.js      # Vite configuration
```

## Tech Stack
- **React 19** - UI framework
- **Vite 8** - Build tool
- **React Router 7** - Routing
- **TanStack Query 5** - Data fetching
- **Zustand** - State management
- **Axios** - HTTP client
- **Tailwind CSS 4** - Styling
- **Lucide React** - Icons

## Backend Integration
The frontend expects the backend API at `http://localhost:8000/api/v1`

Ensure backend is running before starting the dev server:
```bash
# In another terminal
cd backend
uvicorn app.main:app --reload
```
