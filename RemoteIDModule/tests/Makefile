CXX      = g++
CXXFLAGS = -std=c++17 -O2 -Wall -Wno-unused-function \
           -DBOARD_AURELIA_RID_S3 \
           -I stubs -I ..

TARGET   = test_flight_checker
SRC      = test_flight_checker.cpp

.PHONY: all run gen clean

all: $(TARGET)

$(TARGET): $(SRC) stubs/Arduino.h stubs/FS.h stubs/SPIFFS.h stubs/transport.h stubs/spiffs_utils.h \
           ../flight_checker.h ../flight_checker.cpp ../distance_checker.cpp ../parameters.h
	$(CXX) $(CXXFLAGS) -o $@ $(SRC)

# Regenerate all_cases.dat from zones.bin (run after rebuild of zones.bin)
gen:
	python3 gen_all_cases.py

run: $(TARGET) all_cases.dat
	./$(TARGET)

# Build all_cases.dat if missing
all_cases.dat:
	python3 gen_all_cases.py

clean:
	rm -f $(TARGET) all_cases.dat
