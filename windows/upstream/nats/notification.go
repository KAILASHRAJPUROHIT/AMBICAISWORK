package nats

type Notification struct {
	From                   string `json:"from,omitempty"`
	To                     string `json:"to,omitempty"`
	Subject                string `json:"subject,omitempty"`
	MessageTitle           string `json:"message_title,omitempty"`
	MessageGreeting        string `json:"message_greeting,omitempty"`
	MessageText            string `json:"message_text,omitempty"`
	MessageAction          string `json:"message_action,omitempty"`
	MessageActionURL       string `json:"message_action_url,omitempty"`
	MessageAttachFileName  string `json:"message_attach_filename,omitempty"`
	MessageAttachFile      string `json:"message_attach_file,omitempty"`
	MessageAttachFileName2 string `json:"message_attach_filename2,omitempty"`
	MessageAttachFile2     string `json:"message_attach_file2,omitempty"`
}
