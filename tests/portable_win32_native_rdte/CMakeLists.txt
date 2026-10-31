cmake_minimum_required(VERSION 3.20)
project(winebot_native_win32_observer_fixture LANGUAGES C)

# Qualification-only build of preexisting public synthetic sources.
# No observer implementation, application or production source modification.
if(NOT WIN32)
  message(FATAL_ERROR "This fixture qualification requires native Windows")
endif()
add_executable(win_event_observer ../../rdte/wine11/win_event_observer.c)
add_executable(win_event_fixture ../../rdte/wine11/win_event_fixture.c)
target_link_libraries(win_event_observer PRIVATE user32)
target_link_libraries(win_event_fixture PRIVATE user32)
