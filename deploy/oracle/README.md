# Oracle Always Free deployment

One free ARM server holds the API, Qdrant, Postgres, MinIO and the embedding models. Each laptop has the app, Ollama and one chat model.

**State:** written, not yet run on a server. Memory use on 12 GB and speed on 2 ARM CPUs are unmeasured. Until the app relays model requests to the laptop, Deep answers need an Ollama the server can reach, and `/health/ready` reports it as unavailable.

## Steps
1. In Oracle Cloud, create an Ubuntu ARM instance (`VM.Standard.A1.Flex`) with 2 OCPUs and 12 GB. Stay within your account's Always Free limit, because instances over it can be terminated. Add your SSH key.
2. In its subnet's security list, allow inbound TCP 80 and 443. Leave every other port closed.
3. On the server, clone this repository as `LEGAL_RAG`, then run this with the server's IP, using dashes:
   ```bash
   PUBLIC_HOST=1-2-3-4.sslip.io ./deploy/oracle/setup_server.sh
   ```
4. On the Mac:
   ```bash
   ./deploy/oracle/upload_corpus.sh ubuntu@<server-ip>
   ```
5. Check `https://<PUBLIC_HOST>/health`, then enter that address in the app's connection settings.
