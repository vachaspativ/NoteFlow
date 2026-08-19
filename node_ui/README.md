# NoteFlow Node.js UI

This folder contains the optional Node.js / Express proxy and runner for the NoteFlow Web UI.

> [!NOTE]
> NoteFlow includes a built-in Python web server (`fastapi`/`uvicorn`) that runs the full Web UI without requiring Node.js. This `node_ui` package is provided for environments where running an Express server or integrating with Node pipelines is preferred.

## Setup & Running

1. Make sure the NoteFlow Python core is running:
   ```bash
   noteflow --no-browser
   ```

2. Start the Node.js server:
   ```bash
   cd node_ui
   npm install
   npm start
   ```

3. Open `http://localhost:3000` in your browser.
