# BautiAI - Automated AI Video Generation & MCP Server Pipeline

Welcome to **BautiAI** – a high-fidelity automated video generation platform. BautiAI combines a visual, modern React frontend with a secure Python Flask backend playing host to headless browser automation engines (powered by Playwright) and custom AI prompt optimizers.

This platform operates both as an **interactive single-page web app** and a live **Model Context Protocol (MCP) Server + OpenAPI REST Gateway**. This lets external LLMs (like **Claude**, **ChatGPT**, **Cursor**, or custom AI agents) interact directly with BautiAI to generate, track, and retrieve photorealistic and highly cinematic videos.

---

## 🎨 Architecture Overview

```
              +----------------------+
              |   Claude / Cursor    | (Connects via SSE MCP Protocols)
              +----------------------+
                         ||
                         \/
+------------------+     /api/mcp/sse     +------------------------+
|  NVIDIA NIM API  | <==================> |                        |
|  (LLaMA Maverick)|                      |  BautiAI Server        |
+------------------+                      |  (Flask Backend)       |
                                          +------------------------+
+------------------+    Playwright Web                ||
|  Headless Chrome | <------------------              || Serves Static Web App,
|   Virtual Nodes  |                                  \/ SSE & Range Video-Streams
+------------------+                      +------------------------+
                                          |  Vite React Frontend   |
                                          +------------------------+
                                                      ||
                                                      \/
                                          +----------------------+
                                          |    ChatGPT Custom    | (Connects via OpenAPI REST Action)
                                          |     GPT Agents       |
                                          +----------------------+
```

---

## 🚀 Getting Started

When BautiAI launches, it starts both:
1. **The Web Interface** (React Single-Page App) at your local port `3000`.
2. **The Automated Ngrok Tunnel**: Exposes BautiAI to a secure, public web address (e.g., `https://xxxx-xxxx.ngrok-free.app`). 
   * Useful for webhook callbacks.
   * Enables remote LLMs like Claude or ChatGPT to access generated media, screenshots, and tools!

---

## 🤖 1. Model Context Protocol (MCP) Server Setup
BautiAI embeds a compliant, multi-user **Model Context Protocol (MCP)** server natively over **Server-Sent Events (SSE)**.

### A. Connecting Claude Desktop
To grant **Claude Desktop** the power to invent and render videos on your behalf, configure it to connect to your BautiAI server.

1. Open your Claude Desktop configuration file:
   * **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   * **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
2. Add BautiAI as an SSE server (replacing the URL with your active public Ngrok address from the server's console or the Web UI status bar):

```json
{
  "mcpServers": {
    "bautiai": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-sse",
        "https://YOUR-NGROK-SUBDOMAIN.ngrok-free.app/api/mcp/sse"
      ]
    }
  }
}
```

3. Restart Claude Desktop. You will notice a **hollow plug/hammer icon**, indicating Claude has now discovered the BautiAI video tooling suite!

### B. Connecting Cursor IDE or Libby
For editors or clients supporting native SSE integrations:
1. Go to **Settings -> Features -> MCP**.
2. Click **Add New MCP Server**.
3. Fill in:
   * **Name**: `BautiAI`
   * **Type**: `SSE`
   * **URL**: `https://YOUR-NGROK-SUBDOMAIN.ngrok-free.app/api/mcp/sse`

---

## 🔮 2. MCP Tools Reference

Once connected, your AI assistant will have access to the following server capabilities:

### 1. `generate_video` (Text-to-Video)
Starts a background rendering job from a textual description. Generates a unique task ID.
* **Arguments**:
  * `prompt` (string, required): Detailed prompt describing the motion, lighting, and subjects.
  * `model` (string, optional, default `"3.1"`): Target version block. Options: `"3.1"`, `"3.0"`, `"veo-2"`.
  * `aspect_ratio` (string, optional, default `"portrait"`): Target output framing. Options: `"portrait"` (9:16), `"landscape"` (16:9).

### 2. `generate_image_to_video` (Image-to-Video)
Animate subjects relative to a starting keyframe image URL.
* **Arguments**:
  * `image_url` (string, required): A web-accessible HTTP(S) image link (e.g., JPEG, PNG). The server automatically downloads and processes this asset.
  * `prompt` (string, required): Narrative detailing what movement should happen.
  * `model` (string, optional, default `"3.1"`): Engine options.
  * `aspect_ratio` (string, optional, default `"portrait"`): Options: `"portrait"`, `"landscape"`.
  * `aspect_select` (string, optional, default `"vertical"`): Cropper options: `"vertical"`, `"horizontal"`.

### 3. `get_job_status`
Retrieves live processing logs, diagnostic browser screenshots (captured during execution), and the streamable mp4 video once rendering is resolved.
* **Arguments**:
  * `job_id` (string, required): Unique task ID (e.g., `txt-mcp-12345` or `img-mcp-67890`).

### 4. `get_jobs_list`
Lists currently queued, active, and completed jobs.

---

## 💬 3. ChatGPT Custom GPT Actions Integration
OpenAI's ChatGPT (Custom GPTs) cannot connect directly via SSE MCP. Instead, ChatGPT connects using **standard OpenAPI schemas** making REST requests. You can turn ChatGPT into a video director by adding a **Custom Action**.

### How to configure:
1. Go to **ChatGPT -> Explore GPTs -> Create a GPT**.
2. In the Creator Panel, go to **Configure** and click **Create New Action**.
3. Choose **Authentication: None**.
4. Paste the following **OpenAPI Schema** (replace the host with your active `ngrok` URL):

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "BautiAI API Gateway",
    "description": "Exposes automated text-to-video and job status logging tools to ChatGPT.",
    "version": "1.0.0"
  },
  "servers": [
    {
      "url": "https://YOUR-NGROK-SUBDOMAIN.ngrok-free.app",
      "description": "Public BautiAI Production Gateway Tunnel"
    }
  ],
  "paths": {
    "/api/status": {
      "get": {
        "operationId": "checkServerStatus",
        "summary": "Check server pipeline status",
        "responses": {
          "200": {
            "description": "Successful check",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "status": { "type": "string" },
                    "ngrokEnabled": { "type": "boolean" }
                  }
                }
              }
            }
          }
        }
      }
    },
    "/api/generate-video": {
      "post": {
        "operationId": "generateVideo",
        "summary": "Start a new text-to-video generation job",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "prompt": { "type": "string", "description": "Highly descriptive scene details" },
                  "model": { "type": "string", "default": "3.1", "description": "Options: 3.1" },
                  "aspectRatio": { "type": "string", "default": "VIDEO_ASPECT_RATIO_PORTRAIT", "description": "VIDEO_ASPECT_RATIO_PORTRAIT, VIDEO_ASPECT_RATIO_LANDSCAPE" }
                },
                "required": ["prompt"]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Job placed in queue successfully",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "jobId": { "type": "string" },
                    "status": { "type": "string" }
                  }
                }
              }
            }
          }
        }
      }
    },
    "/api/job-status/{job_id}": {
      "get": {
        "operationId": "getJobStatus",
        "summary": "Track video generation progress",
        "parameters": [
          {
            "name": "job_id",
            "in": "path",
            "required": true,
            "schema": { "type": "string" },
            "description": "The unique jobId returned by generateVideo"
          }
        ],
        "responses": {
          "200": {
            "description": "Current status statistics",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "id": { "type": "string" },
                    "status": { "type": "string" },
                    "progress": { "type": "string" },
                    "videoUrl": { "type": "string", "nullable": true },
                    "error": { "type": "string", "nullable": true }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

5. In the Custom GPT instructions, tell ChatGPT:
   ```markdown
   When the user requests to generate a video:
   1. Formulate a highly visual, cinematic description.
   2. Call the 'generateVideo' tool.
   3. Inform the user of the Job ID. Tell them you will track the progress.
   4. Poll 'getJobStatus' every 10-15 seconds until status is 'completed' or 'failed'.
   5. Once 'completed', present the direct video URL. Include a note and link so they can download it!
   ```

---

## 🛠️ 4. HTTP API Endpoint Reference

### A. Prompt Optimizer
#### `POST /api/generate-prompt`
Enhance any simple description into an engineered cinematic description.
* **Payload**:
  ```json
  { "prompt": "a futuristic city" }
  ```
* **Response**:
  ```json
  { "enhancedPrompt": "Stunning hyper-detailed shot of towering glass sky-scrapers integrated with neon vertical gardens, glowing solar-panel walkways, and flying aerodynamic pods slicing through soft evening haze of a solarpunk metropolis..." }
  ```

### B. Text to Video Generator
#### `POST /api/generate-video`
Submit a task onto the browser automation rendering queue.
* **Payload**:
  ```json
  {
    "prompt": "Cinematic shot of neon butterfly in electric forest",
    "model": "3.1",
    "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT"
  }
  ```
* **Response**:
  ```json
  { "jobId": "txt-845129", "status": "queued" }
  ```

### C. Live Performance Tracking
#### `GET /api/job-status/<job_id>`
Queries memory store. Includes screenshots taken at 12s intervals (useful for real-time visual bug checks / troubleshooting).
* **Response example**:
  ```json
  {
    "id": "txt-845129",
    "type": "text-to-video",
    "status": "processing",
    "progress": "Entering prompt on the visual editor...",
    "videoUrl": null,
    "screenshots": [
      "/uploads/shot-txt-845129-1780000.png"
    ],
    "createdAt": 1780823412000
  }
  ```

---

## 📄 Licensing & Technologies
* **Automated Web Driving**: Driven via robust Chromium containers on **Playwright**.
* **Stream Optimization**: Fully compatible with client and mobile media engines utilizing **HTTP 206 Partial Content Range Streaming** for instant seek response.
* **Developer**: Built for multi-modal context connectivity.
