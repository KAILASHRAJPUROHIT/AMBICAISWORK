package nats

type CertificateRequest struct {
	FullName       string   `json:"fullname,omitempty"`
	Email          string   `json:"email,omitempty"`
	Username       string   `json:"username,omitempty"`
	Organization   string   `json:"organization,omitempty"`
	Country        string   `json:"country,omitempty"`
	Province       string   `json:"province,omitempty"`
	Locality       string   `json:"locality,omitempty"`
	Address        string   `json:"address,omitempty"`
	PostalCode     string   `json:"postal_code,omitempty"`
	YearsValid     int      `json:"years_valid,omitempty"`
	MonthsValid    int      `json:"months_valid,omitempty"`
	DaysValid      int      `json:"days_valid,omitempty"`
	Password       string   `json:"password,omitempty"`
	OCSPResponders []string `json:"ocsp_responders,omitempty"`
	ConsoleURL     string   `json:"console_url,omitempty"`
	AgentId        string   `json:"agentId,omitempty"`
	DNSName        string   `json:"dns_name,omitempty"`
}

type AgentCertificateData struct {
	CertBytes       []byte `json:"cert_bytes,omitempty"`
	PrivateKeyBytes []byte `json:"private_key_bytes,omitempty"`
}
