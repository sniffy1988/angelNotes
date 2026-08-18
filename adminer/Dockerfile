FROM adminer:4

USER root

COPY index.php /var/www/html/index.php
COPY angelnotes.php /var/www/html/plugins-enabled/001-angelnotes.php
RUN rm -rf /var/www/html/plugins-enabled/angelnotes.php \
    && chmod 644 /var/www/html/index.php /var/www/html/plugins-enabled/001-angelnotes.php \
    && test -f /var/www/html/plugins-enabled/001-angelnotes.php

USER adminer
