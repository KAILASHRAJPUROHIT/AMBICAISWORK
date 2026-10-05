package utils

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
)

type NetBirdCreateSetupKeyResponse struct {
	ID                  string   `json:"id"`
	Name                string   `json:"name"`
	Expires             string   `json:"expires"`
	Type                string   `json:"type"`
	Valid               bool     `json:"valid"`
	Revoked             bool     `json:"revoked"`
	UsedTimes           int      `json:"used_times"`
	LastUsed            string   `json:"last_used"`
	State               string   `json:"state"`
	AutoGroups          []string `json:"auto_groups"`
	UpdateAt            string   `json:"updated_at"`
	UsageLimit          int      `json:"usage_limit"`
	Ephemeral           bool     `json:"ephemeral"`
	AllowExtraDNSLabels bool     `json:"allow_extra_dns_labels"`
	Key                 string   `json:"key"`
}

type NetBirdPeer struct {
	ID string `json:"id"`
}

func CreateNetBirdOneOffSetupKeyAPI(managementURL string, agentID string, groups string, allowExtraDNSLabels bool, token string) (string, string, error) {

	url := fmt.Sprintf("%s/api/setup-keys", managementURL)

	method := "POST"

	payload := strings.NewReader(fmt.Sprintf(`{
		"name": "OpenUEM %s key",
		"type": "one-off",
		"expires_in": 86400,
		"auto_groups": [ %s ],
		"usage_limit": 1,
		"ephemeral": false,
		"allow_extra_dns_labels": %t
	}`, agentID, groups, allowExtraDNSLabels))

	client := &http.Client{}
	req, err := http.NewRequest(method, url, payload)

	if err != nil {
		return "", "", err
	}

	req.Header.Add("Content-Type", "application/json")
	req.Header.Add("Accept", "application/json")
	req.Header.Add("Authorization", fmt.Sprintf("Token %s", token))

	res, err := client.Do(req)
	if err != nil {
		return "", "", err
	}
	defer res.Body.Close()

	body, err := io.ReadAll(res.Body)
	if err != nil {
		return "", "", err
	}

	response := NetBirdCreateSetupKeyResponse{}
	if err := json.Unmarshal(body, &response); err != nil {
		return "", "", err
	}

	if response.Valid {
		return response.ID, response.Key, nil
	}

	return "", "", errors.New("couldn't parse JSON request")
}

func DeleteNetBirdOneOffSetupKeyAPI(managementURL string, key string, token string) error {
	url := fmt.Sprintf("%s/api/setup-keys/%s", managementURL, key)

	method := "DELETE"

	client := &http.Client{}
	req, err := http.NewRequest(method, url, nil)

	if err != nil {
		return err
	}

	req.Header.Add("Authorization", fmt.Sprintf("Token %s", token))

	res, err := client.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()

	return nil
}

func GetMyNetBirdPeerID(ip string, managementURL string, token string) (string, error) {

	url := fmt.Sprintf("%s/api/peers?ip=%s", managementURL, ip)

	method := "GET"

	client := &http.Client{}
	req, err := http.NewRequest(method, url, nil)

	if err != nil {
		return "", err
	}

	req.Header.Add("Accept", "application/json")
	req.Header.Add("Authorization", fmt.Sprintf("Token %s", token))

	res, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer res.Body.Close()

	body, err := io.ReadAll(res.Body)
	if err != nil {
		return "", err
	}

	peers := []NetBirdPeer{}
	if err := json.Unmarshal(body, &peers); err != nil {
		return "", err
	}

	if len(peers) == 0 {
		return "", errors.New("the API didn't find a peer with this IP address")
	}

	if len(peers) > 2 {
		return "", errors.New("the API found more than one peer with this IP address")
	}

	if peers[0].ID == "" {
		return "", errors.New("could not get the peer ID from the API")
	}

	return peers[0].ID, nil
}

func DeleteNetBirdPeer(peerID string, managementURL string, token string) error {

	url := fmt.Sprintf("%s/api/peers/%s", managementURL, peerID)

	method := "DELETE"

	client := &http.Client{}
	req, err := http.NewRequest(method, url, nil)

	if err != nil {
		return err
	}

	req.Header.Add("Authorization", fmt.Sprintf("Token %s", token))

	res, err := client.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()

	return nil
}

func NetBirdPeerExists(name string, managementURL string, token string) (bool, error) {

	url := fmt.Sprintf("%s/api/peers?name=%s", managementURL, name)

	method := "GET"

	client := &http.Client{}
	req, err := http.NewRequest(method, url, nil)

	if err != nil {
		return false, err
	}

	req.Header.Add("Authorization", fmt.Sprintf("Token %s", token))

	res, err := client.Do(req)
	if err != nil {
		return false, err
	}
	defer res.Body.Close()

	body, err := io.ReadAll(res.Body)
	if err != nil {
		return false, err
	}

	peers := []NetBirdPeer{}
	if err := json.Unmarshal(body, &peers); err != nil {
		return false, err
	}

	return len(peers) > 0, nil
}
