FROM adminer:4

USER root

COPY angelnotes.php /var/www/html/plugins-enabled/001-angelnotes.php
RUN chmod 644 /var/www/html/plugins-enabled/001-angelnotes.php \
    && test -s /var/www/html/plugins-enabled/001-angelnotes.php

USER adminer
