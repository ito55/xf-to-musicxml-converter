A tool to generate a lead sheet (MusicXML) from a single XF-formatted Standard MIDI File (SMF).

This script is designed to solve a specific problem: converting a Yamaha XF-formatted MIDI file, which contains embedded chord data, into a MusicXML lead sheet. It extracts both the chord progressions (from SysEx messages) and the melody (from Channel 1) from a single MIDI file, outputting a MusicXML file ready for use in notation software like Cubase, Dorico, or MuseScore. This streamlines the workflow by avoiding manual separation of melody and chord tracks.

## Features

-   **Chord Extraction**: Parses chord information from both Yamaha XF SysEx messages and standard text/lyric events.
-   **Melody Extraction**: Isolates the melody track (assumed to be on MIDI Channel 1).
-   **Merge Logic**: Intelligently combines chords and melody into a single musical structure.
-   **MusicXML Output**: Generates a standard MusicXML file for easy import into notation software.

## Requirements

-   Python 3.8+
-   `music21`
-   `mido`

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/ito55/xf-to-musicxml-converter.git
    cd xf-to-musicxml-converter
    ```

2.  **Set up a virtual environment (recommended):**
    This creates an isolated environment for the project's dependencies.
    
    ```bash
    # Create a virtual environment named 'venv'
    python -m venv venv
    
    # Activate the virtual environment
    # On Windows:
    .\venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate
    ```

3.  **Install the required Python library:**
    ```bash
    pip install -r requirements.txt
    ```

## Usage

### Generating a Lead Sheet

Run the main script from your terminal, providing the paths to the chord and melody MIDI files, and the desired output path.

```bash
python main.py --input input/your_song.mid --output output/your_song.musicxml
```

-   `--chord-file`: The path to the original XF-formatted MIDI file containing the chord data.
-   `--melody-file`: The path to the MIDI file containing the cleaned-up melody (e.g., on Channel 1).
-   `--output`: The path for the generated MusicXML file.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
