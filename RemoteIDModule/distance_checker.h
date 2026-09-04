#pragma once

#if defined(BOARD_AURELIA_RID_S3)
#include <math.h>
const float EARTH_RADIUS = 6371;

class DistanceCheck{
    public:
    DistanceCheck(){};
        float haversine(double lat1, double lon1, double lat2, double lon2);
        double iE7toFloat(int32_t ie7);
    private:
        double toRadians(double degree);
};
#endif