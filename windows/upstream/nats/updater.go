package nats

import "time"

type OpenUEMUpdateRequest struct {
	Version      string    `json:"version,omitempty"`
	Channel      string    `json:"channel,omitempty"`
	DownloadFrom string    `json:"download,omitempty"`
	DownloadHash string    `json:"download_hash,omitempty"`
	UpdateAt     time.Time `json:"updated_at,omitempty"`
	UpdateNow    bool      `json:"update_now,omitempty"`
}

type FileInfo struct {
	Arch     string `json:"arch,omitempty"`
	Os       string `json:"os,omitempty"`
	FileURL  string `json:"file_url,omitempty"`
	Checksum string `json:"checksum,omitempty"`
}

type OpenUEMRelease struct {
	Version         string     `json:"version,omitempty"`
	Channel         string     `json:"channel,omitempty"`
	Summary         string     `json:"summary,omitempty"`
	ReleaseNotesURL string     `json:"release_notes,omitempty"`
	ReleaseDate     time.Time  `json:"release_date,omitempty"`
	Files           []FileInfo `json:"files,omitempty"`
	IsCritical      bool       `json:"is_critical,omitempty"`
}

const UPDATE_ERROR = "admin.update.agents.task_status_error"
const UPDATE_PENDING = "admin.update.agents.task_status_pending"
const UPDATE_SUCCESS = "admin.update.agents.task_status_success"

func TaskUpdatePossibleStatus() []string {
	return []string{UPDATE_ERROR, UPDATE_PENDING, UPDATE_SUCCESS}
}

type OpenUEMServerRelease struct {
	Version         string                      `json:"version,omitempty"`
	Channel         string                      `json:"channel,omitempty"`
	Summary         string                      `json:"summary,omitempty"`
	ReleaseNotesURL string                      `json:"release_notes,omitempty"`
	ReleaseDate     time.Time                   `json:"release_date,omitempty"`
	Files           map[string][]ServerFileInfo `json:"files,omitempty"`
	IsCritical      bool                        `json:"is_critical,omitempty"`
}

type ServerFileInfo struct {
	Arch     string `json:"arch,omitempty"`
	Os       string `json:"os,omitempty"`
	FileURL  string `json:"file_url,omitempty"`
	Checksum string `json:"checksum,omitempty"`
}
