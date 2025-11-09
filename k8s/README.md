# Kubernetes Deployment Guide

This directory contains Kubernetes manifests for deploying the Markdown Web Browser in a production Kubernetes cluster.

## Architecture

The deployment consists of:

- **Web Pods** (`mdwb-web`): FastAPI servers handling HTTP requests
- **Worker Pods** (`mdwb-worker`): Arq workers processing background jobs
- **Redis**: Job queue for coordinating work between web and workers
- **Persistent Storage**: For captured data and operational logs
- **Autoscaling**: HPA for both web and worker deployments
- **Ingress**: External HTTPS access with optional cert-manager

## Prerequisites

1. **Kubernetes Cluster** (v1.24+)
   - GKE, EKS, AKS, or self-hosted cluster
   - At least 3 nodes with 4 CPU / 8GB RAM each

2. **kubectl** configured to access your cluster

3. **Ingress Controller** (optional, for external access)
   ```bash
   # Install nginx ingress controller
   kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml
   ```

4. **Cert-Manager** (optional, for automatic HTTPS)
   ```bash
   kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
   ```

5. **Metrics Server** (for HPA)
   ```bash
   kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
   ```

## Quick Start

### 1. Create Namespace

```bash
kubectl apply -f namespace.yaml
```

### 2. Create Secrets

Copy the template and fill in your credentials:

```bash
cp secret.yaml.template secret.yaml
# Edit secret.yaml with your API keys
vi secret.yaml
```

Required secrets:
- `OLMOCR_API_KEY`: Get from https://ai2endpoints.cirrascale.ai
- `WEBHOOK_SECRET`: Generate with `openssl rand -hex 32`

Apply the secrets:

```bash
kubectl apply -f secret.yaml
```

**Important**: DO NOT commit `secret.yaml` to git! It's in `.gitignore`.

### 3. Apply Configuration

```bash
kubectl apply -f configmap.yaml
```

### 4. Deploy Redis

```bash
kubectl apply -f redis.yaml
```

Wait for Redis to be ready:

```bash
kubectl wait --for=condition=available --timeout=60s deployment/mdwb-redis -n mdwb
```

### 5. Deploy Web Service

```bash
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
```

Wait for pods to be ready:

```bash
kubectl wait --for=condition=available --timeout=120s deployment/mdwb-web -n mdwb
```

### 6. Deploy Workers

```bash
kubectl apply -f deployment-worker.yaml
```

### 7. Setup Autoscaling

```bash
kubectl apply -f hpa.yaml
```

### 8. Setup Ingress (Optional)

Edit `ingress.yaml` and replace `mdwb.example.com` with your domain:

```bash
vi ingress.yaml  # Update domain
kubectl apply -f ingress.yaml
```

## Deployment Order

**Full deployment in correct order**:

```bash
# 1. Namespace and configuration
kubectl apply -f namespace.yaml
kubectl apply -f secret.yaml
kubectl apply -f configmap.yaml

# 2. Dependencies
kubectl apply -f redis.yaml

# 3. Application
kubectl apply -f deployment.yaml
kubectl apply -f deployment-worker.yaml
kubectl apply -f service.yaml

# 4. Autoscaling and ingress
kubectl apply -f hpa.yaml
kubectl apply -f ingress.yaml
```

## Verification

### Check Pod Status

```bash
kubectl get pods -n mdwb

# Expected output:
# NAME                          READY   STATUS    RESTARTS   AGE
# mdwb-redis-xxx                1/1     Running   0          2m
# mdwb-web-xxx                  1/1     Running   0          1m
# mdwb-web-yyy                  1/1     Running   0          1m
# mdwb-worker-xxx               1/1     Running   0          1m
# mdwb-worker-yyy               1/1     Running   0          1m
# mdwb-worker-zzz               1/1     Running   0          1m
```

### Check Logs

```bash
# Web pods
kubectl logs -f deployment/mdwb-web -n mdwb

# Worker pods
kubectl logs -f deployment/mdwb-worker -n mdwb

# Redis
kubectl logs -f deployment/mdwb-redis -n mdwb
```

### Test Health Endpoint

```bash
# Port forward to local machine
kubectl port-forward -n mdwb service/mdwb-web 8000:80

# Test in another terminal
curl http://localhost:8000/health
```

### Check Metrics

```bash
kubectl port-forward -n mdwb service/mdwb-web 9000:9000
curl http://localhost:9000/metrics
```

## Scaling

### Manual Scaling

```bash
# Scale web pods
kubectl scale deployment mdwb-web --replicas=5 -n mdwb

# Scale worker pods
kubectl scale deployment mdwb-worker --replicas=10 -n mdwb
```

### Autoscaling

Autoscaling is configured via HPA:

```bash
# Check HPA status
kubectl get hpa -n mdwb

# Web HPA: 2-10 pods based on CPU/memory
# Worker HPA: 3-20 pods based on CPU/memory
```

## Resource Sizing

### Small Deployment (< 10 req/min)
- Web: 2 replicas, 500m CPU / 1Gi RAM each
- Workers: 2 replicas, 1 CPU / 2Gi RAM each
- Total: 3 CPU / 6Gi RAM

### Medium Deployment (10-100 req/min)
- Web: 5 replicas, 1 CPU / 2Gi RAM each
- Workers: 5 replicas, 2 CPU / 4Gi RAM each
- Total: 15 CPU / 30Gi RAM

### Large Deployment (100+ req/min)
- Web: 10 replicas, 2 CPU / 4Gi RAM each
- Workers: 15 replicas, 4 CPU / 8Gi RAM each
- Total: 80 CPU / 160Gi RAM

## Storage

### Persistent Volumes

The deployment uses two PVCs:

1. **mdwb-data** (50Gi): Captured data, SQLite database
2. **mdwb-ops** (10Gi): Operational logs, warnings

For production, use a storage class with backup capabilities:

```yaml
# Example: Use GCP Persistent Disk
storageClassName: pd-ssd

# Example: Use AWS EBS
storageClassName: gp3

# Example: Use NFS for shared storage
storageClassName: nfs-client
```

### Cache Storage

Web and worker pods use `emptyDir` for cache (ephemeral). For better performance, use local SSDs:

```yaml
volumes:
  - name: cache
    hostPath:
      path: /mnt/fast-cache
      type: DirectoryOrCreate
```

## Monitoring

### Prometheus Integration

The service is annotated for Prometheus scraping:

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "9000"
  prometheus.io/path: "/metrics"
```

Install Prometheus Operator:

```bash
kubectl apply -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/bundle.yaml
```

### Grafana Dashboards

Key metrics to monitor:

- **Request Rate**: `http_requests_total`
- **Response Time**: `http_request_duration_seconds`
- **Capture Time**: `capture_duration_seconds_sum`
- **OCR Throughput**: `ocr_tiles_processed_total`
- **Queue Depth**: Redis queue lengths
- **Pod Resources**: CPU/memory utilization

## Security

### API Keys

Generate API keys inside a pod:

```bash
kubectl exec -it deployment/mdwb-web -n mdwb -- \
  python scripts/manage_api_keys.py create "production-key" --rate-limit 100
```

Save the generated key and configure clients to use it:

```bash
curl -H "X-API-Key: mdwb_xxxxx" https://mdwb.example.com/jobs
```

### Network Policies

Apply network policies to restrict pod communication:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mdwb-netpol
  namespace: mdwb
spec:
  podSelector:
    matchLabels:
      app: markdown-web-browser
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
  egress:
    - to:
        - podSelector:
            matchLabels:
              component: redis
    - to:  # Allow external OCR API
        - namespaceSelector: {}
      ports:
        - protocol: TCP
          port: 443
```

## Troubleshooting

### Pods Not Starting

```bash
# Describe pod to see events
kubectl describe pod -n mdwb <pod-name>

# Check logs
kubectl logs -n mdwb <pod-name>

# Common issues:
# - Missing secrets: Check secret.yaml is applied
# - Image pull errors: Update image or registry credentials
# - Resource limits: Increase node capacity or reduce limits
```

### Health Check Failures

```bash
# Test health endpoint directly
kubectl exec -it deployment/mdwb-web -n mdwb -- \
  curl http://localhost:8000/health

# Common issues:
# - libvips not installed: Check Dockerfile includes libvips
# - Playwright browsers missing: Run playwright install in image
```

### Redis Connection Issues

```bash
# Test Redis connection
kubectl exec -it deployment/mdwb-redis -n mdwb -- redis-cli ping

# Should return: PONG
```

### Worker Not Processing Jobs

```bash
# Check worker logs
kubectl logs -f deployment/mdwb-worker -n mdwb

# Test job queue manually
kubectl exec -it deployment/mdwb-web -n mdwb -- python -c "
from app.queue import get_queue
import asyncio

async def test():
    queue = await get_queue()
    stats = await queue.get_queue_stats()
    print(stats)

asyncio.run(test())
"
```

## Updating

### Rolling Update

```bash
# Update image tag
kubectl set image deployment/mdwb-web web=markdown-web-browser:v1.2.0 -n mdwb
kubectl set image deployment/mdwb-worker worker=markdown-web-browser:v1.2.0 -n mdwb

# Watch rollout
kubectl rollout status deployment/mdwb-web -n mdwb
kubectl rollout status deployment/mdwb-worker -n mdwb
```

### Rollback

```bash
# Rollback to previous version
kubectl rollout undo deployment/mdwb-web -n mdwb
kubectl rollout undo deployment/mdwb-worker -n mdwb
```

## Cleanup

```bash
# Delete all resources
kubectl delete namespace mdwb

# Or delete individually
kubectl delete -f hpa.yaml
kubectl delete -f ingress.yaml
kubectl delete -f service.yaml
kubectl delete -f deployment-worker.yaml
kubectl delete -f deployment.yaml
kubectl delete -f redis.yaml
kubectl delete -f configmap.yaml
kubectl delete -f secret.yaml
kubectl delete -f namespace.yaml
```

## Advanced Configuration

### Custom Docker Registry

Update image references in deployments:

```yaml
spec:
  template:
    spec:
      imagePullSecrets:
        - name: registry-credentials
      containers:
        - name: web
          image: myregistry.example.com/markdown-web-browser:latest
```

Create registry secret:

```bash
kubectl create secret docker-registry registry-credentials \
  --docker-server=myregistry.example.com \
  --docker-username=user \
  --docker-password=pass \
  --namespace=mdwb
```

### Resource Quotas

Limit total resources for the namespace:

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: mdwb-quota
  namespace: mdwb
spec:
  hard:
    requests.cpu: "100"
    requests.memory: "200Gi"
    persistentvolumeclaims: "10"
```

## Support

For issues or questions:
- GitHub Issues: https://github.com/Dicklesworthstone/markdown_web_browser/issues
- Documentation: See `/docs` directory
