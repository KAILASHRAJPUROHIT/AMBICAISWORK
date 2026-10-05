package nats

import (
	"fmt"
	"log"
	"strconv"
	"strings"

	"github.com/nats-io/nats.go"
)

func ConnectWithNATS(servers, clientCert, clientKey, caCert string, websocketPort string) (*nats.Conn, error) {
	c, err := nats.Connect(
		servers,
		nats.RootCAs(caCert),
		nats.ClientCert(clientCert, clientKey),
		nats.MaxReconnects(-1),
		nats.ReconnectHandler(func(nc *nats.Conn) {
			log.Println("[INFO]: reconnected to the message broker")
		}),
		nats.DisconnectErrHandler(func(nc *nats.Conn, err error) {
			if err != nil {
				log.Printf("[INFO]: disconnected from message broker due to: %s, will attempt reconnect", err.Error())
			}
		}),
		nats.ClosedHandler(func(nc *nats.Conn) {
			log.Printf("[INFO]: connection closed. Reason: %q\n", nc.LastError())
		}),
	)

	if err != nil {

		// Attempt to connect using WebSockets
		if websocketPort == "" {
			return nil, err
		}

		port, err := strconv.Atoi(websocketPort)
		if err != nil {
			log.Printf("[ERROR]: the WebSocker port is not valid")
			return nil, err
		}

		webSocketServers := []string{}
		for s := range strings.SplitSeq(servers, ",") {
			server := strings.Split(s, ":")[0]
			webSocketServers = append(webSocketServers, fmt.Sprintf("wss://%s:%d", server, port))
		}

		c, err = nats.Connect(
			strings.Join(webSocketServers, ","),
			nats.RootCAs(caCert),
			nats.ClientCert(clientCert, clientKey),
			nats.MaxReconnects(-1),
			nats.ReconnectHandler(func(nc *nats.Conn) {
				log.Println("[INFO]: reconnected to the message broker")
			}),
			nats.DisconnectErrHandler(func(nc *nats.Conn, err error) {
				if err != nil {
					log.Printf("[INFO]: disconnected from message broker due to: %s, will attempt reconnect", err.Error())
				}
			}),
			nats.ClosedHandler(func(nc *nats.Conn) {
				log.Printf("[INFO]: connection closed. Reason: %q\n", nc.LastError())
			}),
		)

		if err != nil {
			return nil, err
		}
	}

	log.Println("[INFO]: connection established with NATS server")
	return c, nil
}

func ConnectWithNATSTOKEN(servers, token string) (*nats.Conn, error) {
	c, err := nats.Connect(
		servers,
		nats.Token(token),
		nats.MaxReconnects(-1),
		nats.ReconnectHandler(func(nc *nats.Conn) {
			log.Println("[INFO]: reconnected to the message broker")
		}),
		nats.DisconnectErrHandler(func(nc *nats.Conn, err error) {
			if err != nil {
				log.Printf("[INFO]: disconnected from message broker due to: %s, will attempt reconnect", err.Error())
			}
		}),
		nats.ClosedHandler(func(nc *nats.Conn) {
			log.Printf("[INFO]: connection closed. Reason: %q\n", nc.LastError())
		}),
	)

	if err != nil {
		return nil, err
	}

	log.Println("[INFO]: connection established with NATS server")
	return c, nil
}
