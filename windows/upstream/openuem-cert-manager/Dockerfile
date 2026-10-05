FROM golang:1.26.1 AS build
COPY . ./
COPY --chmod=755 ./scripts/create-certs.sh /bin/create-certs.sh
COPY --chmod=755 ./scripts/generate-nats-conf.sh /bin/generate-nats-conf.sh
COPY --chmod=755 ./scripts/configure.sh /bin/configure.sh
RUN go build -o /bin/openuem-cert-manager .

FROM debian:latest
COPY --from=build /bin/openuem-cert-manager /bin/openuem-cert-manager
COPY --from=build /bin/create-certs.sh /bin/create-certs.sh
COPY --from=build /bin/generate-nats-conf.sh /bin/generate-nats-conf.sh
COPY --from=build /bin/configure.sh /bin/configure.sh
ENTRYPOINT ["/bin/openuem-cert-manager"]