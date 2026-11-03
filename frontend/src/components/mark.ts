// Geometry shared by the logo, the favicon and the preloader, so all three draw the same mark.
export const MARK = {
  viewBox: '8 5.5 36 36',
  // A cloud traced counterclockwise from the bottom left: right lobe, the big top lobe, left lobe.
  cloud: 'M13 37 H35.5 A8 8 0 0 0 37.2 21.2 A11.5 11.5 0 0 0 15.6 17.6 A9.8 9.8 0 0 0 13 37 Z',
  bars: [
    { x: 17.4, y: 28.5, height: 6 },
    { x: 22.4, y: 25, height: 9.5 },
    { x: 27.4, y: 21.5, height: 13 },
  ],
  barWidth: 3.4,
  arrow: 'M10 38.5 C21 36.5 31 29 37.3 15.8',
  arrowHead: '39.6 9.8 40.3 17.4 33.9 14.3',
};
