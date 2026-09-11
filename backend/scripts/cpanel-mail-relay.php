<?php
/**
 * HTTP-to-local-mail bridge for the HRMS (Employee Data Management) app.
 *
 * WHY THIS EXISTS: on hosting platforms that block outbound SMTP (Railway
 * confirmed - both port 465 and 587 time out), direct SMTP from the app to
 * mail.sunlease.in never connects. This script is uploaded to the SAME
 * cPanel server the mailbox lives on, and is called over HTTPS instead
 * (port 443 is never blocked). It then submits the message over SMTP to
 * mail.sunlease.in itself - which, being local traffic on this server's
 * own network, never crosses the boundary the platform's block applies to.
 *
 * Uses a small hand-rolled SMTP client (implicit TLS on port 465 + AUTH
 * LOGIN over a raw socket) instead of PHP's mail() - some hosts disable
 * mail() outright and push everyone onto authenticated SMTP submission -
 * and instead of PHPMailer/Composer, since shared hosting often doesn't
 * have Composer set up. Identical design to sunlease-expms's
 * scripts/cpanel-mail-relay.php; copy this file's SETUP steps exactly but
 * use a DIFFERENT secret and (ideally) a different mailbox/from-address
 * than expms uses, so the two apps' relays are fully independent.
 *
 * SETUP (cPanel File Manager or FTP):
 * 1. Upload this file under public_html at a private, hard-to-guess path -
 *    e.g. public_html/hrms-relay-<random-string>/index.php - NOT a
 *    predictable name like "mail-relay.php". Obscurity of the URL plus the
 *    secret below are this endpoint's only defenses; it has no other auth.
 * 2. Change RELAY_SECRET below to a long random value, e.g. the output of:
 *      openssl rand -hex 32
 * 3. Confirm FROM_EMAIL is a real mailbox on this same server, and set
 *    SMTP_PASSWORD to that mailbox's actual password.
 * 4. In your deployment platform's environment variables, set:
 *      HRMS_MAIL_RELAY_URL=https://sunlease.in/hrms-relay-<random-string>/
 *      HRMS_MAIL_RELAY_SECRET=<the same secret from step 2>
 *    Setting HRMS_MAIL_RELAY_URL switches the backend to use this relay
 *    instead of direct SMTP automatically - no other config needed.
 * 5. Test with:
 *      curl -X POST https://sunlease.in/hrms-relay-<random-string>/ \
 *        -H "X-Relay-Secret: <secret>" -H "Content-Type: application/json" \
 *        -d '{"to":"you@example.com","subject":"Test","body":"Hello"}'
 */

define('RELAY_SECRET', 'CHANGE-ME-TO-A-LONG-RANDOM-SECRET');
define('FROM_EMAIL', 'hrms@sunlease.in');
define('FROM_NAME', 'HRMS — Employee Data Management');
define('MAX_ATTACHMENT_BYTES', 15 * 1024 * 1024); // 15MB

// SMTP submission settings for FROM_EMAIL's own mailbox. Per this server's
// own mail-client settings, port 465 is implicit SSL/TLS (encrypted from
// the first byte), NOT STARTTLS - hence connecting via "ssl://" below.
define('SMTP_HOST', 'mail.sunlease.in');
define('SMTP_PORT', 465); // implicit SSL/TLS submission port
define('SMTP_USERNAME', 'hrms@sunlease.in'); // usually same as FROM_EMAIL
define('SMTP_PASSWORD', 'CHANGE-ME-TO-THE-MAILBOX-PASSWORD');

header('Content-Type: application/json');

function fail(int $code, string $message): void {
    http_response_code($code);
    echo json_encode(['success' => false, 'error' => $message]);
    exit;
}

// Without this, a PHP fatal error (out-of-memory decoding a large
// attachment, a hit against post_max_size, etc.) on this server produces a
// bare 500 with an EMPTY body - since display_errors is off by default on
// cPanel. This shutdown handler intercepts any fatal that happens after
// this point and turns it into a normal JSON error response, plus an
// error_log() line (visible in cPanel > Metrics > Errors) with the real
// cause.
register_shutdown_function(function () {
    $error = error_get_last();
    if ($error === null) {
        return;
    }
    $fatalTypes = [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR, E_USER_ERROR];
    if (!in_array($error['type'], $fatalTypes, true)) {
        return;
    }
    $message = sprintf('%s in %s:%d', $error['message'], $error['file'], $error['line']);
    error_log('[hrms-mail-relay] FATAL: ' . $message);
    if (!headers_sent()) {
        http_response_code(500);
        header('Content-Type: application/json');
    }
    echo json_encode(['success' => false, 'error' => 'Server error: ' . $message]);
});

if (RELAY_SECRET === 'CHANGE-ME-TO-A-LONG-RANDOM-SECRET') {
    fail(500, 'RELAY_SECRET has not been configured on the server - refusing to run with the default value.');
}
if (SMTP_PASSWORD === 'CHANGE-ME-TO-THE-MAILBOX-PASSWORD') {
    fail(500, 'SMTP_PASSWORD has not been configured on the server - refusing to run with the default value.');
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    fail(405, 'POST only');
}

$raw = file_get_contents('php://input');
error_log(sprintf(
    '[hrms-mail-relay] request received: %d bytes, memory_limit=%s, post_max_size=%s',
    strlen($raw), ini_get('memory_limit'), ini_get('post_max_size')
));
$data = json_decode($raw, true);
if (!is_array($data)) {
    fail(400, 'Invalid JSON body');
}

$secret = $_SERVER['HTTP_X_RELAY_SECRET'] ?? ($data['secret'] ?? '');
if (!hash_equals(RELAY_SECRET, (string) $secret)) {
    fail(403, 'Invalid secret');
}

$to = filter_var($data['to'] ?? '', FILTER_VALIDATE_EMAIL);
if (!$to) {
    fail(400, 'Invalid or missing "to" address');
}
$subject = (string) ($data['subject'] ?? '(no subject)');
$body = (string) ($data['body'] ?? '');
$attachmentB64 = $data['attachment_base64'] ?? null;
$attachmentFilename = (string) ($data['attachment_filename'] ?? 'attachment.pdf');
$attachmentMime = (string) ($data['attachment_mime'] ?? 'application/pdf');

$attachmentData = null;
if ($attachmentB64) {
    $attachmentData = base64_decode((string) $attachmentB64, true);
    if ($attachmentData === false) {
        fail(400, 'attachment_base64 is not valid base64');
    }
    if (strlen($attachmentData) > MAX_ATTACHMENT_BYTES) {
        fail(400, 'Attachment too large');
    }
}

$boundary = md5(uniqid((string) microtime(true), true));
$headers = [];
$headers[] = 'From: ' . FROM_NAME . ' <' . FROM_EMAIL . '>';
$headers[] = 'Reply-To: ' . FROM_EMAIL;
$headers[] = 'MIME-Version: 1.0';

if ($attachmentData !== null) {
    $headers[] = 'Content-Type: multipart/mixed; boundary="' . $boundary . '"';

    $message = "--{$boundary}\r\n";
    $message .= "Content-Type: text/plain; charset=UTF-8\r\n";
    $message .= "Content-Transfer-Encoding: 8bit\r\n\r\n";
    $message .= $body . "\r\n\r\n";

    $safeFilename = str_replace(['"', "\r", "\n"], '', $attachmentFilename);
    $message .= "--{$boundary}\r\n";
    $message .= 'Content-Type: ' . $attachmentMime . '; name="' . $safeFilename . "\"\r\n";
    $message .= "Content-Transfer-Encoding: base64\r\n";
    $message .= 'Content-Disposition: attachment; filename="' . $safeFilename . "\"\r\n\r\n";
    $message .= chunk_split(base64_encode($attachmentData));
    $message .= "--{$boundary}--";
} else {
    $headers[] = 'Content-Type: text/plain; charset=UTF-8';
    $message = $body;
}

// Strip anything in the subject that could inject extra headers.
$safeSubject = str_replace(["\r", "\n"], '', $subject);

/**
 * Minimal SMTP client: connect over implicit TLS, AUTH LOGIN, MAIL
 * FROM/RCPT TO/DATA. Throws RuntimeException with the server's own
 * response text on any failure, which fail() below turns into a JSON
 * error - so a bad password or a rejected recipient shows up as a real
 * error message instead of a mystery 500.
 */
function smtp_send(string $host, int $port, string $username, string $password, string $from, string $fromName, string $to, string $subject, array $headers, string $body): void {
    $socket = @stream_socket_client(
        "ssl://{$host}:{$port}", $errno, $errstr, 15,
        STREAM_CLIENT_CONNECT, stream_context_create(['ssl' => ['verify_peer' => true, 'verify_peer_name' => true]])
    );
    if (!$socket) {
        throw new RuntimeException("Could not connect to ssl://{$host}:{$port} - {$errstr} ({$errno})");
    }
    stream_set_timeout($socket, 15);

    $expect = function (string $expectedPrefix) use ($socket, &$lastResponse) {
        $lastResponse = '';
        while (($line = fgets($socket, 515)) !== false) {
            $lastResponse .= $line;
            // Multi-line SMTP responses use "250-" until the final "250 ".
            if (strlen($line) < 4 || $line[3] !== '-') {
                break;
            }
        }
        if (strpos($lastResponse, $expectedPrefix) !== 0) {
            throw new RuntimeException("Unexpected SMTP response (expected {$expectedPrefix}): {$lastResponse}");
        }
        return $lastResponse;
    };
    $send = function (string $command) use ($socket) {
        fwrite($socket, $command . "\r\n");
    };

    try {
        $expect('220');
        $send('EHLO ' . $host);
        $expect('250');

        $send('AUTH LOGIN');
        $expect('334');
        $send(base64_encode($username));
        $expect('334');
        $send(base64_encode($password));
        $expect('235');

        $send('MAIL FROM:<' . $from . '>');
        $expect('250');
        $send('RCPT TO:<' . $to . '>');
        $expect('250');

        $send('DATA');
        $expect('354');

        // $headers already carries 'From:' (set by the caller) - only add
        // the envelope-level headers that aren't part of it.
        $fullHeaders = array_merge([
            'To: ' . $to,
            'Subject: ' . $subject,
            'Date: ' . date('r'),
        ], $headers);
        $dotStuffed = preg_replace('/^\./m', '..', $body); // RFC 5321 dot-stuffing
        $send(implode("\r\n", $fullHeaders) . "\r\n\r\n" . $dotStuffed . "\r\n.");
        $expect('250');

        $send('QUIT');
    } finally {
        fclose($socket);
    }
}

try {
    smtp_send(SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL, FROM_NAME, $to, $safeSubject, $headers, $message);
} catch (Throwable $exc) {
    error_log('[hrms-mail-relay] SMTP send failed: ' . $exc->getMessage());
    fail(502, 'SMTP send failed: ' . $exc->getMessage());
}

echo json_encode(['success' => true]);
