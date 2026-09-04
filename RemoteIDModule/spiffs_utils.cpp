#include "spiffs_utils.h"
/*
const char* SPIFFSUtils::find_string(const char *filename) {
    // Abrir el archivo desde SPIFFS
    File file = SPIFFS.open(filename, "r");
    if (!file) {
        Serial.println("Error: No se pudo abrir el archivo.");
        return nullptr;
    }

    // Obtener el tamaño del archivo comprimido
    size_t fileSize = file.size();
    if (fileSize < 4) {
        Serial.println("Error: Archivo comprimido inválido.");
        file.close();
        return nullptr;
    }

    // Leer los últimos 4 bytes para obtener el tamaño descomprimido
    file.seek(fileSize - 4);
    uint8_t sizeBytes[4];
    file.read(sizeBytes, 4);

    uint32_t decompressed_size = sizeBytes[0] | sizeBytes[1] << 8 | sizeBytes[2] << 16 | sizeBytes[3] << 24;
    Serial.print("Decompressed size: ");
    Serial.println(decompressed_size);

    // Reservar memoria para los datos descomprimidos
    uint8_t *decompressed_data = (uint8_t *)malloc(decompressed_size + 1);
    if (!decompressed_data) {
        Serial.println("Error: No hay suficiente memoria para descomprimir el archivo.");
        file.close();
        return nullptr;
    }
    decompressed_data[decompressed_size] = 0; // Null-terminate

    // Inicializar la estructura de descompresión
    TINF_DATA *d = (TINF_DATA *)malloc(sizeof(TINF_DATA));
    if (!d) {
        Serial.println("Error: No hay suficiente memoria para TINF_DATA.");
        ::free(decompressed_data);
        file.close();
        return nullptr;
    }
    uzlib_uncompress_init(d, NULL, 0);

    // Leer y descomprimir el archivo por partes
    uint8_t buffer[256]; // Ajusta el tamaño según tus necesidades
    d->source = buffer;
    d->dest = decompressed_data;
    d->destSize = decompressed_size;
    d->source_limit = buffer + sizeof(buffer);

    file.seek(0); // Volver al inicio del archivo
    while (file.available()) {
        int bytesRead = file.read(buffer, sizeof(buffer));
        d->source = buffer;
        d->source_limit = buffer + bytesRead;

        int res = uzlib_uncompress(d);
        if (res != TINF_OK) {
            Serial.println("Error: Fallo en la descompresión.");
            ::free(decompressed_data);
            ::free(d);
            file.close();
            return nullptr;
        }
    }

    // Liberar la estructura de descompresión
    ::free(d);
    file.close();

    return (const char *)decompressed_data;
}*/