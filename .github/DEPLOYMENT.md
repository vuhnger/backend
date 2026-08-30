# Deployment

Dette repoet bygger imaget, det deployer det ikke. `build-image.yml` kjører når
CI er grønn på `main`, bygger imaget og pusher det til
`ghcr.io/vuhnger/backend` med både commit-SHA og `latest` som tag.

Selve deployen ligger i [vuhnger/infra](https://github.com/vuhnger/infra) og
kjøres med Kamal derfra. Denne kodebasen vet dermed ikke hvilken server den
kjører på, og infra-repoet bygger aldri applikasjonskode.

## Hva imaget lover

Imaget har `LABEL service="backend"`, som Kamal krever, og en `HEALTHCHECK` som
poller `HEALTH_URL` hvis den er satt. Kamal setter den per rolle, slik at
Docker markerer en hengende container som unhealthy og `autoheal` restarter
den.

## Migrasjoner

Alembic kjøres av infra-repoet før den nye versjonen får trafikk, ikke herfra.
