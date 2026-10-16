param([int]$Port = 7431)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$client = [System.Net.Sockets.TcpClient]::new('127.0.0.1', $Port)
$stream = $client.GetStream()
$stream.ReadTimeout = 120000
$reader = [System.IO.StreamReader]::new($stream, [System.Text.UTF8Encoding]::new($false))
$writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
$writer.AutoFlush = $true
try {
  while ($null -ne ($line = [Console]::ReadLine())) {
    $request = $line | ConvertFrom-Json
    $writer.WriteLine($line)
    do {
      $reply = $reader.ReadLine()
      if ($null -eq $reply) { throw 'Concat desconectado.' }
      [Console]::WriteLine($reply)
      $message = $reply | ConvertFrom-Json
    } while ($null -eq $message.id -or $message.id -ne $request.id)
  }
} finally { $client.Dispose() }
