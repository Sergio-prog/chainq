from chainq.progress import Progress


def test_progress_is_silent_off_tty(capsys):
    with Progress("scanning", 2) as progress:
        progress.advance()
        progress.stage("pricing")
    assert capsys.readouterr().err == ""
