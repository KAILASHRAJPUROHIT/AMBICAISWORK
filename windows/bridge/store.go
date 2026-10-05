package main

import (
	"context"
	"database/sql"
	"errors"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
)

// Disk is one logical drive as the agent reported it.
type Disk struct {
	Label           string `json:"label"`
	Filesystem      string `json:"filesystem"`
	UsagePercent    int    `json:"usagePercent"`
	Size            string `json:"size"`
	Remaining       string `json:"remaining"`
	BitLockerStatus string `json:"bitlockerStatus"`
}

// Antivirus is the product the agent found, if any.
type Antivirus struct {
	Name    string `json:"name"`
	Active  bool   `json:"active"`
	Updated bool   `json:"updated"`
}

// Device is one Windows PC, in the shape the AMBIC console consumes.
type Device struct {
	ID              string     `json:"id"`
	Hostname        string     `json:"hostname"`
	Nickname        string     `json:"nickname"`
	Description     string     `json:"description"`
	IP              string     `json:"ip"`
	MAC             string     `json:"mac"`
	Status          string     `json:"status"` // WaitingForAdmission, Enabled, Disabled
	Online          bool       `json:"online"`
	FirstContactMs  int64      `json:"firstContact"`
	LastContactMs   int64      `json:"lastContact"`
	RestartRequired bool       `json:"restartRequired"`
	Manufacturer    string     `json:"manufacturer"`
	Model           string     `json:"model"`
	Serial          string     `json:"serial"`
	MemoryMB        int64      `json:"memoryMB"`
	CPU             string     `json:"cpu"`
	CPUCores        int64      `json:"cpuCores"`
	OSVersion       string     `json:"osVersion"`
	OSEdition       string     `json:"osEdition"`
	OSDescription   string     `json:"osDescription"`
	OSArch          string     `json:"osArch"`
	Domain          string     `json:"domain"`
	LoggedInUser    string     `json:"loggedInUser"`
	LastBootMs      int64      `json:"lastBoot"`
	UpdateStatus    string     `json:"updateStatus"`
	PendingUpdates  *bool      `json:"pendingUpdates"`
	LastUpdateScan  int64      `json:"lastUpdateSearch"`
	Antivirus       *Antivirus `json:"antivirus"`
	AppCount        int        `json:"appCount"`
	Disks           []Disk     `json:"disks,omitempty"`
}

// ErrNotFound is returned when no Windows PC has the id.
var ErrNotFound = errors.New("device not found")

// Store reads Windows PCs. The real implementation is Postgres (OpenUEM's database); tests use a fake.
type Store interface {
	List(ctx context.Context) ([]Device, error)
	Get(ctx context.Context, id string) (Device, error)
}

type pgStore struct {
	db     *sql.DB
	online time.Duration
}

func newPGStore(url string, online time.Duration) (*pgStore, error) {
	db, err := sql.Open("pgx", url)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(4)
	db.SetConnMaxLifetime(30 * time.Minute)
	return &pgStore{db: db, online: online}, nil
}

const deviceSelect = `
SELECT a.oid, a.hostname, COALESCE(a.nickname,''), COALESCE(a.description,''), COALESCE(a.ip,''), COALESCE(a.mac,''),
       COALESCE(a.agent_status,''), a.first_contact, a.last_contact, COALESCE(a.restart_required,false),
       COALESCE(c.manufacturer,''), COALESCE(c.model,''), COALESCE(c.serial,''), COALESCE(c.memory,0),
       COALESCE(c.processor,''), COALESCE(c.processor_cores,0),
       COALESCE(o.version,''), COALESCE(o.edition,''), COALESCE(o.description,''), COALESCE(o.arch,''),
       COALESCE(o.domain,''), COALESCE(o.username,''), o.last_bootup_time,
       COALESCE(s.system_update_status,''), s.pending_updates, s.last_search,
       av.name, av.is_active, av.is_updated,
       (SELECT count(*) FROM apps p WHERE p.agent_apps = a.oid)
FROM agents a
LEFT JOIN computers c ON c.agent_computer = a.oid
LEFT JOIN operating_systems o ON o.agent_operatingsystem = a.oid
LEFT JOIN system_updates s ON s.agent_systemupdate = a.oid
LEFT JOIN LATERAL (SELECT name, is_active, is_updated FROM antiviri WHERE agent_antivirus = a.oid ORDER BY is_active DESC LIMIT 1) av ON true
WHERE lower(a.os) = 'windows'`

func ms(t sql.NullTime) int64 {
	if !t.Valid {
		return 0
	}
	return t.Time.UnixMilli()
}

func (s *pgStore) scan(rows interface{ Scan(...any) error }) (Device, error) {
	var d Device
	var first, last, boot, scan sql.NullTime
	var pending sql.NullBool
	var avName sql.NullString
	var avActive, avUpdated sql.NullBool
	err := rows.Scan(&d.ID, &d.Hostname, &d.Nickname, &d.Description, &d.IP, &d.MAC,
		&d.Status, &first, &last, &d.RestartRequired,
		&d.Manufacturer, &d.Model, &d.Serial, &d.MemoryMB,
		&d.CPU, &d.CPUCores,
		&d.OSVersion, &d.OSEdition, &d.OSDescription, &d.OSArch,
		&d.Domain, &d.LoggedInUser, &boot,
		&d.UpdateStatus, &pending, &scan,
		&avName, &avActive, &avUpdated,
		&d.AppCount)
	if err != nil {
		return d, err
	}
	d.FirstContactMs, d.LastContactMs, d.LastBootMs, d.LastUpdateScan = ms(first), ms(last), ms(boot), ms(scan)
	if pending.Valid {
		v := pending.Bool
		d.PendingUpdates = &v
	}
	if avName.Valid && avName.String != "" {
		d.Antivirus = &Antivirus{Name: avName.String, Active: avActive.Bool, Updated: avUpdated.Bool}
	}
	d.Online = d.LastContactMs > 0 && time.Since(time.UnixMilli(d.LastContactMs)) <= s.online
	return d, nil
}

func (s *pgStore) List(ctx context.Context) ([]Device, error) {
	rows, err := s.db.QueryContext(ctx, deviceSelect+` ORDER BY lower(a.hostname)`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Device{}
	for rows.Next() {
		d, err := s.scan(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, rows.Err()
}

func (s *pgStore) Get(ctx context.Context, id string) (Device, error) {
	d, err := s.scan(s.db.QueryRowContext(ctx, deviceSelect+` AND a.oid = $1`, id))
	if errors.Is(err, sql.ErrNoRows) {
		return d, ErrNotFound
	}
	if err != nil {
		return d, err
	}
	rows, err := s.db.QueryContext(ctx, `SELECT COALESCE(label,''), COALESCE(filesystem,''), COALESCE(usage,0), COALESCE(size_in_units,''),
		COALESCE(remaining_space_in_units,''), COALESCE(bitlocker_status,'') FROM logical_disks WHERE agent_logicaldisks = $1 ORDER BY label`, id)
	if err != nil {
		return d, err
	}
	defer rows.Close()
	for rows.Next() {
		var k Disk
		if err := rows.Scan(&k.Label, &k.Filesystem, &k.UsagePercent, &k.Size, &k.Remaining, &k.BitLockerStatus); err != nil {
			return d, err
		}
		d.Disks = append(d.Disks, k)
	}
	return d, rows.Err()
}
