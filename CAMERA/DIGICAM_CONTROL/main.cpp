#include <windows.h>
#include <wininet.h>
#include <iostream>

#pragma comment(lib, "wininet.lib")

int main() {
    int totalShots = 4;
    double interval = 0.5; // seconds

    for (int i = 0; i < totalShots; i++) {
        std::cout << "Capturing photo " << (i + 1) << "..." << std::endl;

        HINTERNET hInternet = InternetOpen("CaptureTrigger", INTERNET_OPEN_TYPE_DIRECT, NULL, NULL, 0);
        if (!hInternet) {
            std::cerr << "Failed to open Internet session.\n";
            return 1;
        }

        HINTERNET hConnect = InternetOpenUrl(hInternet, "http://localhost:5513/?CMD=Capture", NULL, 0, INTERNET_FLAG_RELOAD, 0);
        if (!hConnect) {
            std::cerr << "Failed to send capture request.\n";
            InternetCloseHandle(hInternet);
            return 1;
        }

        InternetCloseHandle(hConnect);
        InternetCloseHandle(hInternet);

        Sleep((DWORD)(interval * 1000));  // Sleep in milliseconds
    }

    std::cout << "Capture session complete." << std::endl;
    return 0;
}
