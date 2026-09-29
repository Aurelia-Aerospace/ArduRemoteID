#include "distance_checker.h"

#if defined(BOARD_AURELIA_RID_S3)
double DistanceCheck::toRadians(double degree) {
    return degree * (M_PI / 180.0);
}

float DistanceCheck::haversine(double lat1, double lon1, double lat2, double lon2) {
    lat1 = toRadians(lat1);
    lon1 = toRadians(lon1);
    lat2 = toRadians(lat2);
    lon2 = toRadians(lon2);

    double dLat = lat2 - lat1;
    double dLon = lon2 - lon1;

    double a = pow(sin(dLat / 2), 2) +
               cos(lat1) * cos(lat2) * pow(sin(dLon / 2), 2);
    
    double c = 2 * atan2(sqrt(a), sqrt(1 - a));

    return abs(EARTH_RADIUS * c);
}

double DistanceCheck::iE7toFloat(int32_t ie7){
    //return ie7 / 10000000.0;
    return ie7 * 1.0e-7;
}  
#endif