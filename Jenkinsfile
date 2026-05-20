pipeline {
    agent any

    environment {
        // CHANGE THIS TO YOUR ACTUAL DOCKER HUB USERNAME
        REGISTRY_USER   = 'yuvieee01'

        IMAGE_NAME      = 'crypto-sentiment-ticker'
        IMAGE_TAG       = "${BUILD_NUMBER}" // Automatically uses the Jenkins build number as the tag
        KUBECONFIG_CRED = 'kubeconfig-credentials' // This matches the ID you saved in Step 4.1
    }

    stages {
        stage('Lint & Code Quality') {
            steps {
                echo 'Checking Python code quality...'
                // A quick check to make sure there are no fatal syntax errors in your Python code
                sh 'pip install flake8 && flake8 app.py --count --select=E9,F63,F7,F82 --show-source --statistics'
            }
        }

        stage('Build Docker Image') {
            steps {
                echo "Building version ${IMAGE_TAG}..."
                script {
                    customImage = docker.build("${REGISTRY_USER}/${IMAGE_NAME}:${IMAGE_TAG}")
                }
            }
        }

        stage('Push to Registry') {
            steps {
                echo 'Publishing image to Docker Hub...'
                script {
                    // Uses the Docker Hub credentials you saved in Step 4.1
                    docker.withRegistry('', 'docker-hub-credentials') {
                        customImage.push()
                        customImage.push('latest')
                    }
                }
            }
        }

        stage('Deploy to Kubernetes') {
            steps {
                echo 'Updating the application in the cluster...'
                // Uses the Kubeconfig file you uploaded in Step 4.1
                configFileProvider([configFile(fileId: "${KUBECONFIG_CRED}", variable: 'KUBECONFIG')]) {
                    // Update the deployment image to the newly built tag
                    sh "kubectl set image deployment/crypto-ticker-deployment crypto-ticker-container=${REGISTRY_USER}/${IMAGE_NAME}:${IMAGE_TAG} --kubeconfig=${KUBECONFIG}"
                    
                    // Apply any manifest updates (like service monitors or configuration updates)
                    sh "kubectl apply -f k8s/ --kubeconfig=${KUBECONFIG}"
                }
            }
        }
    }

    post {
        success {
            echo "Pipeline completed successfully! Version ${IMAGE_TAG} is live."
        }
        failure {
            echo "Pipeline failed. Check the logs above to see which stage broke."
        }
    }
}