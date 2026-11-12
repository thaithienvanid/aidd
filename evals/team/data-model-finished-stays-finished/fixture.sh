#!/usr/bin/env bash
set -euo pipefail
# A small shipment model in Go, in a repository that uses aidd: one shipment, its four statuses, and the instants of its events.
# The prompt asks for a fifth status on a delivered shipment. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd shipment
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
cat > go.mod <<'GO'
module example.com/depot

go 1.22
GO
cat > shipment/shipment.go <<'GO'
// Package shipment holds one parcel on its way to a customer.
package shipment

import "time"

// Status is a shipment's place in its life.
type Status string

const (
	Booked    Status = "booked"
	InTransit Status = "in_transit"
	Delivered Status = "delivered"
	Cancelled Status = "cancelled"
)

// Shipment is one parcel. The depot's list shows every shipment that is booked or in transit.
type Shipment struct {
	ID          string
	Status      Status
	BookedAt    time.Time
	DeliveredAt *time.Time
	CancelledAt *time.Time
}
GO
