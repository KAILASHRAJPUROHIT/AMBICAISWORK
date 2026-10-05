FROM golang:1.26.1 AS build
COPY . ./
RUN go build -o "/bin/openuem-ocsp-responder" .

FROM debian:latest
EXPOSE 8000
COPY --from=build /bin/openuem-ocsp-responder /bin/openuem-ocsp-responder
RUN apt-get update && apt-get install -y curl
WORKDIR /tmp
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:${OCSP_PORT}/health || exit 1
ENTRYPOINT ["/bin/openuem-ocsp-responder"]