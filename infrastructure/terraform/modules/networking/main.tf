/**
 * Networking Module
 * VPC, Subnets, Cloud NAT, Private Service Connect
 */

# -----------------------------------------------------------------------------
# VPC Network
# -----------------------------------------------------------------------------

resource "google_compute_network" "main" {
  name                            = "${var.environment}-vpc"
  project                         = var.project_id
  auto_create_subnetworks         = false
  routing_mode                    = "REGIONAL"
  delete_default_routes_on_create = false
}

# -----------------------------------------------------------------------------
# Subnets
# -----------------------------------------------------------------------------

# App Tier Subnet (Cloud Run, GKE)
resource "google_compute_subnetwork" "app_tier" {
  name                     = "${var.environment}-app-subnet"
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.main.id
  ip_cidr_range            = "10.0.1.0/24"
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# Data Tier Subnet (Cloud SQL, Redis)
resource "google_compute_subnetwork" "data_tier" {
  name                     = "${var.environment}-data-subnet"
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.main.id
  ip_cidr_range            = "10.0.2.0/24"
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# ML Tier Subnet (Vertex AI)
resource "google_compute_subnetwork" "ml_tier" {
  name                     = "${var.environment}-ml-subnet"
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.main.id
  ip_cidr_range            = "10.0.3.0/24"
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# -----------------------------------------------------------------------------
# Serverless VPC Access Connector (for Cloud Run)
# -----------------------------------------------------------------------------

resource "google_vpc_access_connector" "serverless" {
  name          = "${var.environment}-vpc-connector"
  project       = var.project_id
  region        = var.region
  network       = google_compute_network.main.id
  ip_cidr_range = "10.8.0.0/28"
  min_instances = 2
  max_instances = 10

  depends_on = [google_compute_network.main]
}

# -----------------------------------------------------------------------------
# Cloud NAT (for egress)
# -----------------------------------------------------------------------------

resource "google_compute_router" "nat_router" {
  name    = "${var.environment}-nat-router"
  project = var.project_id
  region  = var.region
  network = google_compute_network.main.id

  bgp {
    asn = 64514
  }
}

resource "google_compute_router_nat" "main" {
  name                               = "${var.environment}-cloud-nat"
  project                            = var.project_id
  router                             = google_compute_router.nat_router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }

  min_ports_per_vm                    = 64
  max_ports_per_vm                    = 65536
  enable_endpoint_independent_mapping = false

  # Timeouts for long-running ML jobs
  tcp_established_idle_timeout_sec = 1200
  tcp_transitory_idle_timeout_sec  = 30
  udp_idle_timeout_sec             = 30
}

# -----------------------------------------------------------------------------
# Private Services Access (for Cloud SQL, etc.)
# -----------------------------------------------------------------------------

resource "google_compute_global_address" "private_services" {
  name          = "${var.environment}-private-services"
  project       = var.project_id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
}

# -----------------------------------------------------------------------------
# Firewall Rules
# -----------------------------------------------------------------------------

# Allow internal communication
resource "google_compute_firewall" "allow_internal" {
  name        = "${var.environment}-allow-internal"
  project     = var.project_id
  network     = google_compute_network.main.id
  priority    = 1000
  direction   = "INGRESS"
  description = "Allow internal communication between subnets"

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }

  source_ranges = [
    google_compute_subnetwork.app_tier.ip_cidr_range,
    google_compute_subnetwork.data_tier.ip_cidr_range,
    google_compute_subnetwork.ml_tier.ip_cidr_range,
    google_vpc_access_connector.serverless.ip_cidr_range,
  ]
}

# Allow GCP health checks
resource "google_compute_firewall" "allow_health_checks" {
  name        = "${var.environment}-allow-health-checks"
  project     = var.project_id
  network     = google_compute_network.main.id
  priority    = 1000
  direction   = "INGRESS"
  description = "Allow GCP health checks"

  allow {
    protocol = "tcp"
    ports    = ["80", "443", "8080", "8000"]
  }

  source_ranges = [
    "35.191.0.0/16",   # GCP health check ranges
    "130.211.0.0/22",
  ]

  target_tags = ["allow-health-check"]
}

# Allow IAP for SSH access
resource "google_compute_firewall" "allow_iap" {
  name        = "${var.environment}-allow-iap"
  project     = var.project_id
  network     = google_compute_network.main.id
  priority    = 1000
  direction   = "INGRESS"
  description = "Allow IAP tunnel connections"

  allow {
    protocol = "tcp"
    ports    = ["22", "3389"]
  }

  source_ranges = ["35.235.240.0/20"]  # IAP IP range

  target_tags = ["allow-iap"]
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "network_id" {
  value = google_compute_network.main.id
}

output "network_name" {
  value = google_compute_network.main.name
}

output "app_subnet_id" {
  value = google_compute_subnetwork.app_tier.id
}

output "data_subnet_id" {
  value = google_compute_subnetwork.data_tier.id
}

output "ml_subnet_id" {
  value = google_compute_subnetwork.ml_tier.id
}

output "vpc_connector_id" {
  value = google_vpc_access_connector.serverless.id
}

output "private_services_address" {
  value = google_compute_global_address.private_services.name
}
