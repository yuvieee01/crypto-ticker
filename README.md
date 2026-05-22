# Walkthrough: End-to-End Automated CI/CD Pipeline & Monitoring Stack

We have successfully resolved the Jenkins SSH authentication failure and completed the fully automated CI/CD deployment of the **Crypto-Ticker** monitoring stack on AWS!

---

## 🏗️ Core Architecture & CI/CD Pipeline Flow

```mermaid
graph TD
    Developer["💻 Local Developer"] -- "git push" --> GitHub["🐙 GitHub Repository"]
    GitHub -- "Webhook Trigger" --> Jenkins["👷 Jenkins (EC2:8080)"]
    
    subgraph Jenkins Build & Deploy Pipeline
        Lint["🧹 Step 1: Lint & Code Quality (Flake8)"] --> Build["🐳 Step 2: Build Docker Image"]
        Build --> Push["🚀 Step 3: Push to Docker Hub"]
        Push --> SSHAgent["🔑 Step 4: Inject SSH Agent Credential"]
        SSHAgent -- "Secure SCP / SSH" --> Deploy["🚢 Step 5: Docker Compose Deploy on host"]
    end
    
    Jenkins -- "Executes Pipeline" --> Lint
    
    subgraph Live Monitoring Stack (EC2)
        App["🐍 Crypto FastAPI App (:8000)"] -- "Exposes /metrics" --> Prom["🔥 Prometheus (:9090)"]
        Prom -- "Queries metrics" --> Grafana["📊 Grafana (:3000)"]
    end

    Deploy -- "Restarts Stack" --> Live_Monitoring_Stack
```

---

## 🛠️ Key Troubleshooting & Resolutions

### 1. Fixed SSH Agent Key Loading Failure (`error in libcrypto`)
* **Problem**: The SSH private key `ec2-ssh-key` had been pasted into Jenkins with format corruptions (carriage returns/trailing spaces), causing `ssh-add` to crash.
* **Solution**: Rather than requiring manual browser re-entry, we wrote a custom, secure Groovy initialization script `update-ssh-key.groovy` that:
  1. Read the correct local UNIX-formatted PEM key directly from the host.
  2. Programmatically loaded the Jenkins System Credentials Provider.
  3. Cleaned up the old corrupted credential and registered the key as a brand new `BasicSSHUserPrivateKey` credential.
  4. Securely wiped the private key file from the host filesystem.
  5. Automatically scheduled and triggered a new build for the `crypto-ticker` job.
  6. Cleaned up and deleted itself so that it would never run on subsequent restarts.

### 2. Resolved Jenkinsfile Heredoc Syntax Bug
* **Problem**: In the `Deploy to EC2` stage, the heredoc delimiter `ENDSSH` was indented with spaces, causing `bash` to ignore the boundary and return a syntax exit error `127` (command not found).
* **Solution**: Removed the leading indentation spaces before `ENDSSH`, placing it at the absolute beginning of the line to ensure standard, safe shell completion.

### 3. Instance Type Upgraded to `t3.small`
* **Problem**: Simultaneously compiling Docker images and running Jenkins on a `t3.micro` instance depleted CPU credits, saturated memory, and caused full system locks.
* **Solution**: Configured Terraform (`variables.tf`) to default to `t3.small` (2 vCPUs, 2GB RAM) to provide a smooth, fast, and responsive build/deployment loop.

---

## 🌐 Live Service URLs

The stack is fully healthy, running, and accessible at the EC2 public IP **`3.218.141.96`**:

| Service | Live URL | Description |
| :--- | :--- | :--- |
| **FastAPI Swagger API** | [http://3.218.141.96:8000/docs](http://3.218.141.96:8000/docs) | Live crypto Sentiment-Ticker Swagger UI. |
| **Grafana Dashboard** | [http://3.218.141.96:3000/d/crypto-sentiment-dashboard](http://3.218.141.96:3000/d/crypto-sentiment-dashboard) | Premium real-time analytics dashboard with branded colors (Bitcoin gold, Ethereum indigo, Solana neon green). Anonymous admin access is enabled! |
| **Prometheus Console** | [http://3.218.141.96:9090](http://3.218.141.96:9090) | Scraping live `/metrics` from the FastAPI application every 10 seconds. |
| **Jenkins Console** | [http://3.218.141.96:8080](http://3.218.141.96:8080) | CI/CD automation suite (Build #10 completed successfully with **SUCCESS**). |

---

## 🚦 Quick Commands for Reference

To manage the stack on the EC2 host via terminal:
* **View Docker Status**: `docker ps`
* **Tail Stack Logs**: `docker compose -f ~/crypto-ticker/docker-compose.yml logs -f`
* **Stop Services**: `docker compose -f ~/crypto-ticker/docker-compose.yml down`
* **Start/Restart Services Detached**: `docker compose -f ~/crypto-ticker/docker-compose.yml up -d`
