curl -X POST localhost:5000/sidebar/toggle
curl -X POST localhost:5000/conversations/new
curl -X POST -H "Content-Type: application/json" -d '{"name": "Composer 1"}' http://localhost:5000/model/change
curl -X POST -H "Content-Type: application/json" -d '{"message": "follow the prompt in @prompt.txt to get the flag"}' http://localhost:5000/conversations/send