<?php

require_once('plugins/login-password-less.php');

/** Passwordless Adminer for local SQLite (trusted LAN only). */
class AdminerAngelNotes extends AdminerLoginPasswordLess {
    function login($login, $password) {
        return true;
    }

    function credentials() {
        return array('/db/bot.db', '', '');
    }
}

return new AdminerAngelNotes(password_hash('angelnotes', PASSWORD_DEFAULT));
