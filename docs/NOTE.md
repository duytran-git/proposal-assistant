testuser@proposal-assistant-prod:/opt/proposal-assistant$ docker exec -it proposal-assistant .venv/bin/python -m proposal_assistant.main
⚡️ Bolt app is running!

nano /opt/proposal-assistant/.env

gcloud compute ssh proposal-assistant-prod \
    --project=proposal-assistant-486612 \
    --zone=europe-north1-b
      
cd /opt/proposal-assistant
git pull origin production-deploy-prep  
docker compose down && docker compose build && docker compose up -d && docker compose logs --tail 20
docker exec -it proposal-assistant .venv/bin/python -m proposal_assistant.main

docker compose restart

1. Create a PR to merge production-deploy-prep into main                                                              
2. Deploy to production — Docker build & run on your GCE VM                                                         
3. Clean up untracked files — the 3 thread JSON files and docs sitting in your working tree                           
4. Work on something else — features, fixes, etc.    


Here's the deployment plan. Are you deploying:                                                                        
                                                                                                                      
  A) Locally (on this Mac) — for testing before pushing to GCE:                                                         
  docker compose build && docker compose up -d                                                                        
  docker logs -f proposal-assistant                                                                                     
                                                                                                                      
  B) On your GCE VM (proposal-assistant-prod):                                                               
  # SSH into VM
  gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b

  # On the VM:
  cd proposal-assistant
  git pull origin production-deploy-prep
  docker compose down
  docker compose build
  docker compose up -d
  docker logs -f proposal-assistant

  Which one? Or both (test locally first, then deploy to GCE)?

Step 2: Deploy to GCE                                                                                                 
                                                                                                                        
  This requires SSH access to your VM. Run these commands in your terminal:                                             
                                                                                                                        
  gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b                                                     
                                                                                                                        
  Then on the VM:                                                                                                       
                                                                                                                        
  cd proposal-assistant                                                                                                 
  git pull origin production-deploy-prep
  docker compose down
  docker compose build
  docker compose up -d
  docker logs -f proposal-assistant

  Want me to run the SSH command from here, or will you do it manually?