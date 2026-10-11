FROM php:7.4-cli-bullseye
RUN printf '%s\n' \
          'deb http://archive.debian.org/debian bullseye main' \
          'deb http://archive.debian.org/debian-security bullseye-security main' \
          'deb http://archive.debian.org/debian bullseye-updates main' \
          > /etc/apt/sources.list \
     && printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99no-check-valid-until \
     && apt-get update \
     && apt-get install -y --no-install-recommends libpq-dev \
     && docker-php-ext-install pgsql \
     && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV PHP_CLI_SERVER_WORKERS=4
CMD ["php", "-d", "display_errors=0", "-S", "0.0.0.0:8080", "-t", "public", "public/router.php"]
