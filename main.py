from laundry_alarm import LaundryAlarm


def main():
    laundry = LaundryAlarm()
    try:
        while True:
            laundry.check()
    finally:
        laundry.cleanup()


if __name__ == '__main__':
    main()
