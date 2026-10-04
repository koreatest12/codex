package io.github.koreatest12.codex.biff;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PiiMaskerTest {
    @Test
    void masksReservation() {
        assertEquals("********1234", PiiMasker.mask("reservation", "ABCD56781234"));
    }

    @Test
    void masksPhone() {
        assertEquals("***-****-5678", PiiMasker.mask("phone", "010-1234-5678"));
    }

    @Test
    void masksEmail() {
        assertEquals("k***@e***.com", PiiMasker.mask("email", "kwonn@example.com"));
    }

    @Test
    void rejectsUnknownKind() {
        assertThrows(IllegalArgumentException.class, () -> PiiMasker.mask("password", "secret"));
    }
}
