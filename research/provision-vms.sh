#!/bin/bash
# =============================================================================
# Provision Azure VMs for Docker Performance Research
# Two identical VMs, different storage tiers
# 
# Prerequisites: az login (already authenticated)
# Estimated cost: ~$3-5 total (run benchmarks, then delete)
# =============================================================================

RESOURCE_GROUP="rg-docker-research"
LOCATION="eastus"
VM_SIZE="Standard_D2s_v3"       # 2 vCPU, 8GB RAM (from your paper)
IMAGE="Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest"
ADMIN_USER="opscart"
SSH_KEY="~/.ssh/id_rsa.pub"     # Change if your key is elsewhere

# =============================================================================
# Step 1: Create Resource Group
# =============================================================================
echo "Creating resource group..."
az group create \
    --name $RESOURCE_GROUP \
    --location $LOCATION

# =============================================================================
# Step 2: VM with Premium SSD (P10 — up to 500 IOPS, 100 MB/s)
# =============================================================================
echo ""
echo "Creating VM: docker-research-premium-ssd..."
az vm create \
    --resource-group $RESOURCE_GROUP \
    --name docker-research-premium-ssd \
    --size $VM_SIZE \
    --image $IMAGE \
    --admin-username $ADMIN_USER \
    --ssh-key-values $SSH_KEY \
    --storage-sku Premium_LRS \
    --os-disk-size-gb 64 \
    --public-ip-sku Standard \
    --nsg-rule SSH \
    --output table

# =============================================================================
# Step 3: VM with Standard HDD (up to 500 IOPS, 60 MB/s)
# =============================================================================
echo ""
echo "Creating VM: docker-research-standard-hdd..."
az vm create \
    --resource-group $RESOURCE_GROUP \
    --name docker-research-standard-hdd \
    --size $VM_SIZE \
    --image $IMAGE \
    --admin-username $ADMIN_USER \
    --ssh-key-values $SSH_KEY \
    --storage-sku Standard_LRS \
    --os-disk-size-gb 64 \
    --public-ip-sku Standard \
    --nsg-rule SSH \
    --output table

# =============================================================================
# Step 4: Get IP addresses
# =============================================================================
echo ""
echo "============================================"
echo " VM IP Addresses"
echo "============================================"

PREMIUM_IP=$(az vm show \
    --resource-group $RESOURCE_GROUP \
    --name docker-research-premium-ssd \
    --show-details \
    --query publicIps -o tsv)

HDD_IP=$(az vm show \
    --resource-group $RESOURCE_GROUP \
    --name docker-research-standard-hdd \
    --show-details \
    --query publicIps -o tsv)

echo "Premium SSD:  ssh ${ADMIN_USER}@${PREMIUM_IP}"
echo "Standard HDD: ssh ${ADMIN_USER}@${HDD_IP}"

# =============================================================================
# Step 5: Bootstrap script (run on EACH VM after SSH)
# =============================================================================
cat << 'BOOTSTRAP'

============================================
 Run this on EACH VM after SSH:
============================================

# Install Docker
sudo apt-get update
sudo apt-get install -y docker.io jq bc git

# Start Docker
sudo systemctl enable docker
sudo systemctl start docker

# Verify
docker --version
sudo docker run --rm alpine echo "Docker works!"

# Clone repo and run benchmark
git clone https://github.com/opscart/docker-internals-guide.git
cd docker-internals-guide
git checkout feature/research-datapoints
cd research

# For Premium SSD VM:
sudo bash statistical-benchmark.sh 50 azure-premium-ssd

# For Standard HDD VM:
sudo bash statistical-benchmark.sh 50 azure-standard-hdd

# After benchmark completes, push results:
git config user.name "Shamsher Khan"
git config user.email "shamsher.khan.research@gmail.com"
git add results/
git commit -m "research: add benchmark data (<platform>)"
git push

BOOTSTRAP

# =============================================================================
# CLEANUP (run after benchmarks are done and data is pushed)
# =============================================================================
cat << 'CLEANUP'

============================================
 Cleanup (after all benchmarks complete):
============================================

az group delete --name rg-docker-research --yes --no-wait

# This deletes EVERYTHING: both VMs, disks, NICs, IPs
# Estimated cost before cleanup: ~$3-5 total

CLEANUP